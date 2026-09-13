"""Azure Sandbox lifecycle, private mappings, bounded execution and cost leases."""
import asyncio
import base64
import io
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import sqlite3
import time
import uuid
import zipfile
from .config import ROOT, STATE
from .azure_budget import AzureBudget, RATES
from .azure_transport import AzureTransport, AzureError
from .limits import sandbox_environment

PROFILES = {
    'quick': {'group': 'lab-quick', 'disk': 'python-3.12-code-interpreter', 'cpu': '1000m', 'memory': '2048Mi', 'seconds': 600, 'retained_limit': 1, 'active_limit':1, 'idle_seconds':600, 'suspend_mode':'Disk'},
    'headless': {'group': 'lab-headless', 'disk': 'azure-dev', 'cpu': '2000m', 'memory': '4096Mi', 'seconds': 3600, 'retained_limit': 1, 'active_limit':1, 'idle_seconds':600, 'suspend_mode':'Memory'},
    'developer': {'group': 'lab-developer', 'disk': 'azure-dev', 'cpu': '4000m', 'memory': '8192Mi', 'seconds': 3600, 'retained_limit': 1, 'active_limit':1, 'idle_seconds':600, 'suspend_mode':'Memory'},
}


# Sandbox CPU, memory and disk are a single Azure tier.  The image is separate
# from this choice; changing a tier never needs a new image build.
SIZES={'light':{'cpu':'1000m','memory':'2048Mi','disk_gib':20,'hourly_usd':.108},'balanced':{'cpu':'2000m','memory':'4096Mi','disk_gib':40,'hourly_usd':.216},'performance':{'cpu':'4000m','memory':'8192Mi','disk_gib':80,'hourly_usd':.432}}

class CapacityBusy(RuntimeError): pass


class AzureRuntime:
    def __init__(self, root=None, config=None, transport=None):
        self.root = Path(root or STATE/'azure-runtime'); self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root/'config.json'
        self.config = config if config is not None else (json.loads(path.read_text()) if path.exists() else {})
        self.transport = transport or AzureTransport(self.config)
        self.db = sqlite3.connect(self.root/'workspaces.sqlite', timeout=20)
        self.db.execute('CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, kind TEXT, name TEXT, body TEXT)')
        self.db.commit(); (self.root/'workspaces.sqlite').chmod(0o600)
        self.budget = AzureBudget(self.root/'budget.sqlite', initial=self.config.get('initial_compute_usd', .01))
        self.lock = asyncio.Lock(); self.workspace_locks = {}; self.exec_slots = asyncio.Semaphore(32); self.services = {}; self.service_ready = {}; self.error = None
        self.last_bill_check=0;self.billing_error=None
        self.active_commands = {}
        self.activities = {}; self.queued = {}; self.admission_generation = 0
        from .telemetry import Telemetry
        from .warm_pool import WarmPool
        self.telemetry = Telemetry(self.root/'telemetry.sqlite')
        self.warm = WarmPool(self)
        from .azure_storage import AzureStorage
        self.storage = AzureStorage(self)
        from .editor_profiles import EditorProfiles
        self.editor_profiles=EditorProfiles(self)
        self.resizing=set()

    def configured(self):
        if any(not self.config.get(k) for k in ('subscription_id', 'resource_group', 'region')):
            raise RuntimeError('Azure runtime configuration is missing. Run scripts/setup_azure_runtime.py.')

    def record(self, wid):
        row = self.db.execute('SELECT body FROM workspaces WHERE id=?', (wid,)).fetchone()
        if not row:
            raise RuntimeError('Workspace mapping is unavailable. Inspect the saved workspace ledger before opening it.')
        return json.loads(row[0])

    def records(self, kind=None):
        return [json.loads(row[0]) for row in self.db.execute('SELECT body FROM workspaces WHERE kind=?' if kind else 'SELECT body FROM workspaces', (kind,) if kind else ())]

    def save(self, record):
        with self.db:
            self.db.execute('INSERT INTO workspaces VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,name=excluded.name',
                            (record['id'], record['kind'], record['name'], json.dumps(record)))

    def touch(self, wid):
        record=self.record(wid);record['last_activity_at']=time.time();self.save(record)

    def rate(self, record):
        return SIZES[record.get("compute_size","performance")]["hourly_usd"] if record["kind"]=="developer" else RATES[record["kind"]]

    def allocation(self, record):
        profile=self.profile(record["kind"])
        if record["kind"]=="developer": profile.update(SIZES[record.get("compute_size","performance")])
        return profile

    def profile(self, kind):
        result = dict(PROFILES[kind])
        result.update(self.config.get('profiles', {}).get(kind, {}))
        # CPU/memory and lease maxima are budget policy, not arbitrary overrides.
        if result['cpu'] != PROFILES[kind]['cpu'] or result['memory'] != PROFILES[kind]['memory']:
            raise RuntimeError('Reprice the pilot before changing CPU or memory.')
        if not 30 <= result['seconds'] <= PROFILES[kind]['seconds']: raise RuntimeError('Invalid sandbox lease')
        if type(result['retained_limit']) is not int or not 1 <= result['retained_limit'] <= 5000:
            raise RuntimeError('Invalid retained workspace limit')
        if type(result['active_limit']) is not int or not 1 <= result['active_limit'] <= result['retained_limit']: raise RuntimeError('Invalid running workspace limit')
        if not 60 <= result['idle_seconds'] <= 600 or result['suspend_mode'] not in ('Disk','Memory'): raise RuntimeError('Invalid suspend policy')
        return result

    async def create(self, kind, name, wid=None, *, disposable=False, warm=False, owner=None, compute_size=None):
        self.configured()
        from .identity import current_owner
        owner=owner or current_owner.get()
        if kind=='developer' and compute_size is not None and compute_size not in SIZES:raise ValueError('Unknown compute size')
        if kind != 'quick' and not disposable and not self.config.get('persistent_storage_reviewed'):
            raise RuntimeError('Persistent Azure storage is awaiting a verified price and cost approval. Disposable tests are enabled; existing files are preserved.')
        if not warm:
            self.warm.demand(kind,compute_size)
            await self.warm.retire_mismatched(kind,compute_size)
        async with self.lock:
            previous = next((r for r in self.records(kind) if name in (r['name'],r.get('display_name')) and r['state'] != 'deleted' and not r.get('warm') and r.get('owner')==owner), None)
            record = previous or (self.warm.claim(kind,name,disposable=disposable,compute_size=compute_size) if not warm else None)
            if record is None:
                record={'id':wid or str(uuid.uuid4()),'name':name,'kind':kind,'state':'creating','created_at':time.time(),'updated_at':time.time(),'sandbox_id':None,'disposable':disposable or kind=='quick','warm':warm}
                if kind=='developer':record['compute_size']=compute_size or 'light'
                self.save(record)
            if owner and not warm:record['owner']=owner;self.save(record)
        return await self.start(record['id'],standby=warm)

    async def start(self, wid, *, standby=False):
        if wid in self.resizing:raise RuntimeError('Workspace size is changing. Please wait.')
        kind=self.record(wid)['kind']
        if not standby:self.warm.demand(kind)
        self.queued[kind]=self.queued.get(kind,0)+1
        begin=time.monotonic(); generation=self.admission_generation
        try:
            async with self.workspace_locks.setdefault(wid,asyncio.Lock()):
                while True:
                    if generation!=self.admission_generation:raise RuntimeError('Compute admission was cancelled by Stop all')
                    try:
                        result=await self._start(self.record(wid))
                        self.telemetry.event(kind,wid,'admitted',seconds=time.monotonic()-begin)
                        return result
                    except CapacityBusy:
                        if standby:raise
                        await asyncio.sleep(1)
        finally:self.queued[kind]-=1

    async def _start(self, record):
        started = time.monotonic(); stages = {}
        profile = self.allocation(record); group = profile['group']
        if record['state'] == 'deleted': raise RuntimeError('Workspace has been deleted')
        if record.get('sandbox_id'):
            current = await self.transport.call('get', group, record['sandbox_id'])
            if current['state'] == 'Running' and record.get('prepared') and record.get('lease_until',0) > time.time()+30:
                await self.ensure_services(record); return self.workspace(record, current)
        else:
            # A timed-out create is recovered by an immutable broker-generated label.
            found = [s for s in await self.transport.call('list', group) if s.get('labels',{}).get('lab-workspace') == record['id'] and s['id'] not in record.get('previous_sandboxes',[])]
            if len(found) > 1: raise RuntimeError('Ambiguous Azure create: inspect matching sandboxes before continuing')
            if found:
                record['sandbox_id'] = found[0]['id']; self.save(record)
            elif record.get('create_submitted'):
                raise RuntimeError('Azure create outcome is unconfirmed. Reconcile this operation before retrying; no duplicate sandbox was created.')
        if record.get('charge'):
            self.budget.finish(record.pop('charge'), self.rate(record)*max(0,time.time()-record['lease_started'])/3600)
            self.save(record)
        # Atomic resource admission, separate from slow startup work. Waiting
        # sessions do not allocate compute. A budget guard caps aggregate burn.
        async with self.lock:
            live=await self.transport.call('list',group)
            if not record.get('sandbox_id') and len(live)>=profile['retained_limit']:
                raise RuntimeError('Saved workspace quota reached; raise the Azure group quota without deleting user work.')
            active=[r for r in self.records() if r['id']!=record['id'] and r['state'] in ('running','starting','failed') and r.get('charge')]
            remote_active=sum(v['id']!=record.get('sandbox_id') and v['state'] not in ('Stopped','Suspended') for v in live)
            if max(remote_active,sum(r['kind']==record['kind'] for r in active))>=profile['active_limit']:
                raise CapacityBusy('Waiting for an available compute slot')
            hourly=sum(self.rate(r) for r in active)+self.rate(record)
            if hourly>self.config.get('max_hourly_compute_usd',12):
                raise CapacityBusy('Waiting for the compute cost envelope')
            lease=self.budget.reserve(record['kind'],self.rate(record)*(profile['seconds']+240)/3600)
            record.update(charge=lease,lease_started=time.time(),lease_until=time.time()+profile['seconds'],state='starting')
            self.save(record)
        try:
            if not record.get('sandbox_id'):
                record['create_submitted'] = True; self.save(record)
                current = await self.transport.call('create', group, args={
                    'disk': None if profile.get('disk_id') or record.get('snapshot_id') else profile['disk'], 'disk_id':None if record.get('snapshot_id') else profile.get('disk_id'), 'snapshot_id':record.get('snapshot_id'), 'cpu': profile['cpu'], 'memory': profile['memory'],
                    'auto_suspend_seconds': min(profile['idle_seconds'], profile['seconds']), 'auto_suspend_mode':profile['suspend_mode'],
                    'labels': {'lab-workspace': record['id'], 'lab-kind': record['kind'], 'lab-managed': 'sandbox-lab'},
                })
                record['sandbox_id'] = current['id']; self.save(record)
            else:
                current = await self.transport.call('get', group, record['sandbox_id'])
                if current['state'] != 'Running': current = await self.transport.call('resume', group, record['sandbox_id'])
            stages['azure_allocate_or_resume_seconds'] = round(time.monotonic()-started,3)
            await self.bootstrap(record)
            stages['bootstrap_seconds'] = round(time.monotonic()-started-stages['azure_allocate_or_resume_seconds'],3)
            if record.get('source_restore'):
                await self.restore_source(record)
                stages['source_restore_seconds'] = round(time.monotonic()-started-sum(stages.values()),3)
            record.update(state='running', prepared=True, updated_at=time.time(), last_activity_at=time.time()); self.save(record)
            await self.ensure_services(record)
            record['startup_timings'] = {**stages, 'total_seconds':round(time.monotonic()-started,3)}
            self.save(record)
            self.telemetry.event(record['kind'],record['id'],'started',seconds=time.monotonic()-started)
            return self.workspace(record, current)
        except BaseException as error:
            self.telemetry.event(record['kind'],record['id'],'start_failed',error=str(error))
            record['state'] = 'failed'; self.save(record)
            # Retain reservation and remote ID on uncertain completion. The
            # maintenance worker still stops or deletes the timed-out lease.
            raise

    def workspace(self, record, remote=None):
        state = record['state']
        if remote:
            state = {'Running':'running','Stopped':'stopped','Suspended':'stopped','Creating':'starting','Resuming':'starting','Stopping':'stopping','Deleting':'deleting'}.get(remote['state'], 'unknown')
            if state == 'running' and not record.get('prepared'): state = 'starting'
        return {'id': record['id'], 'name': record.get('display_name',record['name']), 'provider': 'azure', 'kind': record['kind'],
                'template_id': 'azure-'+record['kind'], 'owner_name': record.get('owner','unassigned'), 'deleted': state == 'deleted',
                'created_at': self.iso(record['created_at']), 'latest_build': {'id': record['id'], 'status': state,
                    'updated_at': self.iso(record['updated_at']), 'resources': [{'agents': [{'status':'connected','lifecycle_state':'ready'}]}] if state == 'running' else []}}

    @staticmethod
    def iso(stamp):
        from datetime import datetime, timezone
        return datetime.fromtimestamp(stamp, timezone.utc).isoformat()

    async def get(self, wid):
        record = self.record(wid)
        if not record.get('sandbox_id') or record['state'] == 'deleted': return self.workspace(record)
        remote = await self.transport.call('get', self.profile(record['kind'])['group'], record['sandbox_id'])
        return self.workspace(record, remote)

    async def list(self, kind):
        # One group read, not one request per workspace. Reading never resumes.
        remote = {s['id']:s for s in await self.transport.call('list', self.profile(kind)['group'])}
        result = []
        for record in self.records(kind):
            if record['state'] == 'deleted' or record.get('warm'): continue
            actual = remote.get(record.get('sandbox_id'))
            if record.get('sandbox_id') and actual is None:
                result.append(self.workspace({**record, 'state':'unknown'}))
            else: result.append(self.workspace(record, actual))
        return result

    async def root_exec(self, record, command):
        result = await self.transport.call('exec', self.profile(record['kind'])['group'], record['sandbox_id'], {'command': command})
        if result['exit_code']: raise RuntimeError('Azure runtime preparation failed: '+result.get('stderr','')[-1500:])
        return result['stdout']

    async def bootstrap(self, record):
        group = self.profile(record['kind'])['group']; sid = record['sandbox_id']
        # All root commands below are broker source, never model/workspace text.
        init = (ROOT/'sandbox/azure_bootstrap.py').read_text()
        await self.root_exec(record, 'python -I -c '+shlex.quote(init))
        if record.get('home_restore'):
            archive=Path(record['home_restore'])
            if archive.parent!=self.root/'home-transfers' or archive.is_symlink():raise RuntimeError('Invalid saved home transfer')
            remote='/var/lib/lab/home-restore.tgz'
            await self.root_exec(record,"python -I -c "+shlex.quote("from pathlib import Path; p=Path('"+remote+"'); p.unlink(missing_ok=True); p.touch(mode=0o644)"))
            with archive.open('rb') as file:
                while chunk:=file.read(8_000_000):
                    await self.transport.write(group,sid,remote+'.part',chunk)
                    await self.root_exec(record,"python -I -c "+shlex.quote("from pathlib import Path; p=Path('"+remote+"'); f=p.open('ab'); f.write(Path('"+remote+".part').read_bytes()); f.close()"))
            script="import os,pwd,tarfile,uuid; user=pwd.getpwnam('sandbox'); source=open('"+remote+"','rb'); os.rename(user.pw_dir,'/var/lib/lab/home-before-restore-'+uuid.uuid4().hex); os.mkdir(user.pw_dir,0o755); os.chown(user.pw_dir,user.pw_uid,user.pw_gid); os.setgroups([]); os.setgid(user.pw_gid); os.setuid(user.pw_uid); tarfile.open(fileobj=source).extractall(user.pw_dir,filter='data')"
            await self.root_exec(record,'python -I -c '+shlex.quote(script))
            await self.transport.call('remove_file',group,sid,{'path':remote})
            await self.transport.call('remove_file',group,sid,{'path':remote+'.part'})
            record['home_transfer_backup']=record.pop('home_restore');self.save(record)
        # One immutable bundle transfer, only when the trusted runtime changed.
        names = ['azure_execute.py','azure_bridge.py','quick.py','checkpoint.py','collect.py','plot_capture.py','render_plot.py','package_setup.py']
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in names: archive.writestr(zipfile.ZipInfo(name), (ROOT/'sandbox'/name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
            if record['kind'] != 'quick':
                import websockets
                package = Path(websockets.__file__).parent
                for file in sorted(package.rglob('*.py')):
                    archive.writestr(zipfile.ZipInfo('websockets/'+str(file.relative_to(package))), file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
            if record['kind'] == 'developer':
                folder = ROOT/'sandbox/pi-chat'
                for file in sorted(folder.rglob('*')):
                    if file.is_file() and not file.is_symlink():
                        archive.writestr(zipfile.ZipInfo('pi-chat/'+str(file.relative_to(folder))), file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        bundle = output.getvalue(); digest = hashlib.sha256(bundle).hexdigest()
        check = "from pathlib import Path; p=Path('/opt/lab/runtime.sha256'); print(p.read_text() if p.is_file() else '')"
        installed = (await self.root_exec(record, 'python -I -c '+shlex.quote(check))).strip()
        if installed != digest:
            await self.transport.write(group, sid, '/var/lib/lab/runtime.zip', bundle)
            unpack = "import zipfile; from pathlib import Path; zipfile.ZipFile('/var/lib/lab/runtime.zip').extractall('/opt/lab'); Path('/opt/lab/runtime.sha256').write_text("+repr(digest)+")"
            await self.root_exec(record, 'python -I -c '+shlex.quote(unpack))
        if record['kind']=='quick':return
        # Reset the relay and its single-sandbox credential each runtime lease.
        record['bridge_token'] = secrets.token_urlsafe(48)
        await self.transport.write(group, sid, '/var/lib/lab/bridge.json', json.dumps({'token':record['bridge_token'], 'developer':record['kind']=='developer', 'deadline':record['lease_until']}).encode())
        launcher = "import os,signal,subprocess; from pathlib import Path\np=Path('/var/lib/lab/bridge.pid')\nif p.exists():\n try:\n  pid=int(p.read_text())\n  if b'/opt/lab/azure_bridge.py' in Path('/proc',str(pid),'cmdline').read_bytes(): os.kill(pid,signal.SIGTERM)\n except (ProcessLookupError,FileNotFoundError): pass\nf=open('/var/lib/lab/bridge.log','ab'); child=subprocess.Popen(['python','/opt/lab/azure_bridge.py'],cwd='/opt/lab',stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True); p.write_text(str(child.pid))"
        await self.root_exec(record, 'python -I -c '+shlex.quote(launcher))
        port = await self.transport.call('bridge_port', group, sid)
        from urllib.parse import urlsplit
        parsed = urlsplit(port['url'])
        if parsed.scheme != 'https' or parsed.hostname != f'{sid}--18443.{self.config["region"]}.adcproxy.io':
            raise RuntimeError('Azure returned an unexpected relay endpoint')
        record['bridge_url'] = port['url'].rstrip('/'); self.save(record)
        await self.verify_bridge(record)
        # Package preferences point only to the reverse broker connection. Azure
        # default-deny egress remains the authoritative bypass boundary.
        result = await self.execute(record['id'], ['python','/opt/lab/package_setup.py'], limits={}, timeout=30, bootstrap=True,
                                    environment_setup=True)
        if result['exit_code']: raise RuntimeError('Could not configure sandbox package access')
        if self.profile(record['kind']).get('preinstalled_tools'):
            # Login shells reset PATH. Expose the preinstalled SDK entrypoints
            # from a normal root-owned system PATH directory as well.
            links = {'go':'/usr/local/go/bin/go','rustup':'/usr/local/cargo/bin/rustup','rustc':'/usr/local/cargo/bin/rustc',
                     'cargo':'/usr/local/cargo/bin/cargo','dotnet':'/usr/share/dotnet/dotnet','julia':'/usr/local/julia/bin/julia'}
            script = "from pathlib import Path\nfor name,target in "+repr(links)+".items():\n p=Path('/usr/local/bin')/name\n if not p.exists(): p.symlink_to(target)\n"
            await self.root_exec(record,'python -I -c '+shlex.quote(script))
            result = await self.execute(record['id'], ['sh','/opt/lab/project-init.sh'], timeout=30, bootstrap=True)
            if result['exit_code']: raise RuntimeError('Preinstalled language environment initialization failed')
        if record['kind'] == 'developer': await self.install_ide(record)

    async def verify_bridge(self, record):
        import httpx
        async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
            for attempt in range(10):
                response = await client.get(record['bridge_url']+'/tcp/3000')
                if response.status_code == 401: return
                await asyncio.sleep(.5)
        raise RuntimeError('Relay authentication could not be verified; no preview will be exposed')

    async def install_ide(self, record):
        if self.profile('developer').get('preinstalled_tools'):
            return await self.launch_ide(record, '/usr/local/bin/code-server')
        archive = STATE/'bin/code-server-linux-amd64.tar.gz'
        if not archive.exists(): raise RuntimeError('The verified Linux AMD64 VS Code archive is missing; run scripts/setup_azure_runtime.py --tools.')
        import hashlib
        lock = json.loads((ROOT/'scripts/tool-downloads.lock.json').read_text())['code-server-4.106.3-linux-amd64.tar.gz']
        if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']: raise RuntimeError('VS Code archive integrity check failed')
        group = self.profile('developer')['group']
        check = "from pathlib import Path; p=Path('/opt/lab/ide.sha256'); print(p.read_text() if p.is_file() and Path('/opt/lab/ide/code-server-4.106.3-linux-amd64/bin/code-server').is_file() else '')"
        if (await self.root_exec(record, 'python -I -c '+shlex.quote(check))).strip() != lock['sha256']:
            await self.transport.write(group, record['sandbox_id'], '/var/lib/lab/code-server.tar.gz', archive.read_bytes())
            command = "import tarfile; from pathlib import Path\np=Path('/opt/lab/ide'); p.mkdir(exist_ok=True)\ntarfile.open('/var/lib/lab/code-server.tar.gz').extractall(p,filter='data'); Path('/opt/lab/ide.sha256').write_text("+repr(lock['sha256'])+")"
            await self.root_exec(record, 'python -I -c '+shlex.quote(command))
        executable = '/opt/lab/ide/code-server-4.106.3-linux-amd64/bin/code-server'
        await self.root_exec(record,'python -I -c '+shlex.quote("from pathlib import Path; p=Path('/opt/lab/bin'); p.mkdir(exist_ok=True); link=p/'code-server'; link.unlink(missing_ok=True); link.symlink_to("+repr(executable)+")"))
        await self.launch_ide(record, executable)

    async def launch_ide(self, record, executable):
        await self.editor_profiles.restore(record)
        script = (ROOT/'sandbox/editor_setup.py').read_text()+'\nlaunch('+repr(executable)+')'
        result = await self.execute(record['id'], ['python','-I','-c',script], timeout=30, bootstrap=True)
        if result['exit_code']: raise RuntimeError('VS Code could not start')
        health = "import time,urllib.request\nfor attempt in range(100):\n try:\n  response=urllib.request.urlopen('http://127.0.0.1:13337/healthz',timeout=.5)\n  if response.status==200: break\n except OSError: pass\n time.sleep(.1)\nelse: raise RuntimeError('VS Code health check failed')"
        await self.root_exec(record,'python -I -c '+shlex.quote(health))

    async def execute(self, wid, argv, **kwargs):
        from .activity import background_activity
        tracked=not kwargs.get('bootstrap',False)
        foreground=tracked and not background_activity.get()
        if foreground:self.touch(wid);self.warm.demand(self.record(wid)['kind'])
        if tracked:self.active_commands[wid]=self.active_commands.get(wid,0)+1
        began=time.monotonic()
        try:
            result=await self._execute(wid,argv,**kwargs)
            if foreground:self.telemetry.event(self.record(wid)['kind'],wid,'command',seconds=time.monotonic()-began,exit_code=result.get('exit_code'))
            return result
        except BaseException as error:
            if foreground:self.telemetry.event(self.record(wid)['kind'],wid,'command_failed',seconds=time.monotonic()-began,error=str(error))
            raise
        finally:
            if tracked:self.active_commands[wid]-=1
            if foreground:self.touch(wid);self.warm.demand(self.record(wid)['kind'])

    async def _execute(self, wid, argv, *, stdin='', cwd='/home/sandbox/project', timeout=60, maximum=1_000_000,
                      limits=None, bootstrap=False, environment_setup=False):
        record = self.record(wid)
        if not bootstrap and (record['state']!='running' or record.get('lease_until',0) <= time.time() or self.budget.status()['blocked']):
            raise RuntimeError('Sandbox execution lease expired; reopen it to reserve another bounded lease.')
        if not isinstance(argv, list) or not argv or not all(isinstance(a,str) and '\0' not in a for a in argv): raise ValueError('Invalid command')
        if not bootstrap: await self.ensure_services(record)
        if environment_setup:
            script = (ROOT/'sandbox/package_setup.py').read_text()
            argv = ['python','-I','-c',script]
        group = self.profile(record['kind'])['group']; sid = record['sandbox_id']; ident = uuid.uuid4().hex
        request = {'argv':argv,'stdin':stdin,'cwd':cwd,'timeout':timeout,'maximum':maximum,'limits':sandbox_environment() if limits is None else limits}
        async with self.exec_slots:
            await self.transport.write(group, sid, f'/var/lib/lab/requests/{ident}.request', json.dumps(request).encode())
            launcher = 'import subprocess; subprocess.Popen('+repr(['python','-I','/opt/lab/azure_execute.py',ident])+',stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)'
            await self.root_exec(record, 'python -I -c '+shlex.quote(launcher))
            async with asyncio.timeout(timeout+45):
                while True:
                    if not bootstrap and self.record(wid)['state']!='running':
                        raise RuntimeError('Workspace stopped while this command was running; no further file reads were sent.')
                    try:
                        raw = await self.transport.read(group, sid, f'/var/lib/lab/requests/{ident}.result', maximum+200000)
                        result = json.loads(raw)
                        break
                    except AzureError as error:
                        if error.status_code != 404: raise
                    await asyncio.sleep(.4)
            for suffix in ('request','result'):
                await self.transport.call('remove_file', group, sid, {'path':f'/var/lib/lab/requests/{ident}.{suffix}'})
            return result

    async def ensure_services(self, record):
        if record['kind'] == 'quick' or not record.get('bridge_url'): return
        task = self.services.get(record['id'])
        if not task or task.done():
            if task:
                # Retrieve any previous exception before replacing the task.
                await asyncio.gather(task,return_exceptions=True)
            from .azure_services import serve
            event=asyncio.Event();self.service_ready[record['id']]=event
            task = asyncio.create_task(serve(self, record,event))
            self.services[record['id']] = task
            def completed(result):
                event.clear()
                if not result.cancelled() and result.exception() is not None:
                    self.error = 'Azure package/model connection ended; reopen the workspace to reconnect.'
            task.add_done_callback(completed)
        waiter = asyncio.create_task(self.service_ready[record['id']].wait())
        try:
            done, _ = await asyncio.wait((task, waiter), timeout=20, return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                await task
                raise RuntimeError('Azure package/model connection closed')
            if waiter not in done: raise RuntimeError('Azure package/model connection did not become ready')
        finally:
            waiter.cancel(); await asyncio.gather(waiter, return_exceptions=True)

    def is_idle(self, record):
        from .previews import previews
        last=max(record.get('last_activity_at',record.get('updated_at',0)),self.activities.get(record['kind'],{}).get(record['id'],0))
        return (record['state']=='running'
                and time.time()-last >= self.profile(record['kind'])['idle_seconds']
                and record['id'] not in self.resizing
                and not self.active_commands.get(record['id'])
                and record['id'] not in previews.active_workspaces())

    async def stop(self, wid, *, delete=False, only_if_idle=False):
        async with self.workspace_locks.setdefault(wid,asyncio.Lock()):
            record = self.record(wid)
            # Activity may have resumed while maintenance waited for startup.
            if only_if_idle and not self.is_idle(record): return
            if record['state'] == 'deleted' or (record['state']=='stopped' and not delete): return
            if not record.get('sandbox_id'):
                if record.get('create_submitted'): raise RuntimeError('Reconcile the pending Azure create before cleanup')
                record['state'] = 'deleted'; self.save(record); return
            if record['kind'] != 'quick' and not record.get('disposable') and record['state'] == 'running':
                try:
                    if record['kind']=='developer':await self.editor_profiles.capture(record)
                    await self.backup_source(record)
                    record = self.record(wid)
                except Exception:
                    record['storage_error'] = 'Cloud source checkpoint failed; the sandbox disk is retained.'
                    self.save(record)
            task = self.services.pop(wid, None)
            if task: task.cancel(); await asyncio.gather(task, return_exceptions=True)
            record['state'] = 'deleting' if delete else 'stopping'; self.save(record)
            await self.transport.call('delete' if delete else 'stop', self.profile(record['kind'])['group'], record['sandbox_id'])
            if record.get('charge'):
                self.budget.finish(record.pop('charge'), self.rate(record)*max(0,time.time()-record['lease_started'])/3600)
            record.update(state='deleted' if delete else 'stopped', updated_at=time.time(), prepared=False)
            record.setdefault('first_exit_at',time.time())
            self.telemetry.event(record['kind'],wid,'deleted' if delete else 'stopped')
            self.save(record)

    async def resize(self,wid,size):
        if size not in SIZES:raise ValueError('Unknown compute size')
        record=self.record(wid)
        if record['kind']!='developer':raise ValueError('This workspace cannot change size')
        if record.get('compute_size','performance')==size:return await self.get(wid)
        if wid in self.resizing or self.active_commands.get(wid):raise RuntimeError('Wait for the current workspace operation to finish')
        await self.start(wid)
        self.resizing.add(wid)
        try:
            # A snapshot cannot change a Sandbox tier.  Copy only durable source
            # to Blob, then rebuild a clean home and re-apply the portable editor
            # profile.  The previous stopped sandbox remains a recovery point.
            # This avoids serializing caches and node_modules (which made a
            # nominal size change wait for multi-gigabyte home transfers).
            if not self.storage.enabled:raise RuntimeError('Fast resize needs the approved Blob source checkpoint; original workspace retained')
            await self.editor_profiles.capture(self.record(wid))
            await self.backup_source(self.record(wid))
            await self.stop(wid)
            async with self.workspace_locks.setdefault(wid,asyncio.Lock()):
                record=self.record(wid)
                record.setdefault('previous_sandboxes',[]).append(record['sandbox_id'])
                record.pop('snapshot_id',None)
                record.update(source_restore=True,sandbox_id=None,compute_size=size,create_submitted=False,state='creating',prepared=False)
                self.save(record)
                from .previews import previews
                await previews.remove_workspace(wid)
                return await self._start(record)
        finally:self.resizing.discard(wid)

    async def backup_source(self, record):
        if not self.storage.enabled: return
        from .limits import script_with_limits
        from .workspace_links import checked_files
        # This is source-only, with the same path, size and symlink policy used
        # by source sync. Packages and credentials remain in their own homes.
        result = await self.execute(record['id'],['python','-I','-c',script_with_limits((ROOT/'sandbox/project_files.py').read_text())],
            stdin=json.dumps({'action':'export','path':''}), maximum=70_000_000, timeout=45, bootstrap=True)
        if result['exit_code']: raise RuntimeError('Source checkpoint export failed')
        payload = json.loads(result['stdout']); files = checked_files(payload)
        await self.storage.save('workspaces',record['id'],{'files':files,'kind':record['kind']})
        current = self.record(record['id']); current['last_checkpoint_at'] = time.time(); current.pop('storage_error',None); self.save(current)

    async def restore_source(self, record):
        payload=await self.storage.load('workspaces',record['id'])
        files=(payload or {}).get('files',[])
        # `backup_source` already validates this exact bounded file format.
        from .workspace_links import checked_files
        files=checked_files({'files':files})
        changes=[{'path':item['path'],'before':None,'data':item['data'],'mode':0o600} for item in files]
        result=await self.execute(record['id'],['python','-I','-c',(ROOT/'sandbox/sync_project.py').read_text()],stdin=json.dumps({'scope':'','changes':changes}),bootstrap=True,timeout=45,maximum=1_000_000)
        if result['exit_code'] or len(json.loads(result['stdout']).get('applied',[]))!=len(changes):
            raise RuntimeError('New workspace could not restore its source; original workspace retained')
        current=self.record(record['id']);current.pop('source_restore',None);self.save(current)

    async def maintain(self):
        while True:
            self.telemetry.sample(self)
            if time.time()-self.last_bill_check>300:
                try:await self.refresh_bill();self.billing_error=None
                except Exception:self.billing_error='Azure billing refresh is unavailable; local reservations remain in force.'
                self.last_bill_check=time.time()
            for record in self.records():
                if record['state'] in ('deleted','stopped'): continue
                if record['kind']=='developer' and record['state']=='running' and not record.get('warm') and time.time()-record.get('activity_checked_at',0)>30:
                    try:
                        remote=await self.transport.call('get',self.profile('developer')['group'],record['sandbox_id'])
                        if remote['state']=='Running':
                            # Inspect only timestamps, not session contents. Polling
                            # itself must not keep idle compute or previews alive.
                            script="from pathlib import Path; import json\np=Path.home()/'.config/lab/activity.json'\nprint(p.stat().st_mtime if p.is_file() else 0)"
                            result=await self.execute(record['id'],['python','-I','-c',script],bootstrap=True,timeout=10)
                            at=min(float(result['stdout'].strip()),time.time())
                            current=self.record(record['id']);current['activity_checked_at']=time.time()
                            if at>current.get('last_activity_at',0):
                                current['last_activity_at']=at
                                from .previews import previews
                                if time.time()-at<60:previews.renew_workspace(record['id']);self.warm.demand('developer')
                            self.save(current);record=current
                    except Exception:pass
                idle=self.is_idle(record)
                expired=bool(record.get('lease_until')) and record['lease_until'] <= time.time()
                forced=expired or self.budget.status()['blocked']
                if forced or idle:
                    try: await self.stop(record['id'], delete=record.get('disposable',False), only_if_idle=not forced); self.error = None
                    except Exception: self.error = 'Azure cleanup is unconfirmed. Cost reservations remain; inspect the runtime ledger.'
                elif record['kind'] != 'quick' and not record.get('disposable') and record['state'] == 'running' and time.time()-record.get('last_checkpoint_at',0)>60:
                    try:
                        # A read-only status check must precede any file export:
                        # an autosuspended VM must never be woken by backup.
                        remote = await self.transport.call('get',self.profile(record['kind'])['group'],record['sandbox_id'])
                        if remote['state'] == 'Running': await self.backup_source(record)
                    except Exception:
                        current = self.record(record['id']); current['storage_error'] = 'Cloud source checkpoint needs attention; local and sandbox files are retained.'; self.save(current)
            await asyncio.sleep(10)

    async def refresh_bill(self):
        self.configured()
        url='https://management.azure.com/subscriptions/'+self.config['subscription_id']+'/resourceGroups/'+self.config['resource_group']+'/providers/Microsoft.Consumption/budgets/sandbox-lab-testing-200?api-version=2024-08-01'
        process=await asyncio.create_subprocess_exec('sh',str(ROOT/'scripts/azure_pilot_az.sh'),'rest','--method','GET','--url',url,'--output','json',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            out,_=await asyncio.wait_for(process.communicate(),30)
            if process.returncode or len(out)>100000:raise RuntimeError('Budget read failed')
            data=json.loads(out)['properties']['currentSpend']
            if data['unit']!='USD':raise RuntimeError('Budget currency changed')
            self.budget.refresh_billed(float(data['amount']))
        finally:
            if process.returncode is None:process.kill();await process.wait()

    async def close(self):
        for record in self.records():
            if record['state'] in ('deleted','stopped'):continue
            try:await self.stop(record['id'],delete=record.get('disposable',False))
            except Exception:self.error='Azure shutdown cleanup is unconfirmed; reservations remain.'
        tasks=list(self.services.values())
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if hasattr(self.transport, 'close'): await self.transport.close()


_runtime = None
def runtime():
    global _runtime
    if _runtime is None: _runtime = AzureRuntime()
    return _runtime
