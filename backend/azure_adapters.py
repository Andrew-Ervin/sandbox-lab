"""App-facing Azure adapters. Legacy wire fields keep saved project links stable."""
import asyncio
import base64
import json
import re
import time
import uuid
from .activity import Activity
from .config import ROOT
from .limits import value, script_with_limits
from .azure_runtime import runtime


class NoReserve:
    record = {}
    def request(self): pass  # Chat may request a warm hint; Azure stays on demand.
    def protected(self, wid): return False
    def status(self): return {'enabled':False,'ready':False,'state':'On demand · Azure pilot','workspace_id':None,'error':None,'target':0,'idle_seconds':0,'claims':0,'always_on':False}
    async def maintain(self, store): await asyncio.Event().wait()


class AzureWorkspaces:
    provider = 'azure'
    def __init__(self, kind):
        self.kind = kind; self.runtime = runtime(); self.token = ''
        self.active = set(); self.provisioning = set(); self.touched = Activity('azure-'+kind)
        self.runtime.activities[kind]=self.touched
        self.provision_lock = asyncio.Lock(); self.lock = self.provision_lock
        self.max_running = self.runtime.profile(kind)['active_limit']
        self.project_locks = {}; self.slots = asyncio.Semaphore(self.max_running)
        self.reserve = NoReserve()
        self.tasks = {}; self.harness = {}; self.configured_until = {}; self.capability_until = {}; self.setup_errors = {}; self.renewal_error = None

    @property
    def native_active(self): return self.sessions.active_workspaces if hasattr(self,'sessions') else set()

    def settings(self): return {'provider':'azure','token':'','template_id':'azure-'+self.kind,'organization_id':'azure'}

    async def api(self, method, path, **kwargs):
        """Compatibility at the existing app boundary; never contacts Azure."""
        if method == 'GET' and path == '/api/v2/workspaces': return {'workspaces':await self.runtime.list(self.kind)}
        if method == 'GET' and path == '/api/v2/users/me':
            from .identity import current_owner
            self.runtime.configured(); return {'id':current_owner.get()}
        if method == 'GET' and path.startswith('/api/v2/templates/'):
            return {'id':'azure-'+self.kind,'active_version_id':'azure-v1'}
        match = re.fullmatch(r'/api/v2/workspaces/([a-f0-9-]{36})(/builds)?',path)
        if not match: raise RuntimeError('This operation is not supported by the Azure runtime')
        wid = match[1]; record = self.runtime.record(wid)
        if record['kind'] != self.kind: raise RuntimeError('Workspace profile mismatch')
        if method == 'GET' and not match[2]: return await self.runtime.get(wid)
        if method == 'POST' and match[2]:
            transition = kwargs.get('json',{}).get('transition')
            if transition == 'start': return await self.runtime.start(wid)
            if transition in ('stop','delete'):
                await self.runtime.stop(wid,delete=transition=='delete'); return await self.runtime.get(wid)
        raise RuntimeError('This operation is not supported by the Azure runtime')

    async def ready(self):
        try: self.runtime.configured(); await self.runtime.list(self.kind); return True
        except Exception: return False

    async def execute(self, workspace, argv, **kwargs):
        if self.runtime.record(workspace['id'])['kind'] != self.kind: raise RuntimeError('Workspace profile mismatch')
        return await self.runtime.execute(workspace['id'],argv,**kwargs)

    async def invoke(self, workspace, script, payload=None, timeout=60, maximum=70_000_000):
        result = await self.execute(workspace,['python','-I','-c',script_with_limits(script)],
                                    stdin=json.dumps(payload) if payload is not None else '', timeout=timeout, maximum=maximum)
        if result['exit_code']: raise RuntimeError('Azure workspace command failed: '+result.get('stderr','')[:300])
        return result['stdout']

    async def collect_artifacts(self, workspace):
        code = (ROOT/'sandbox/collect.py').read_text().replace("Path('/workspace/artifacts')", "Path('/home/sandbox/project/artifacts')")
        return json.loads(await self.invoke(workspace,code,maximum=value('ARTIFACT_MAX_TOTAL_BYTES')*2+1_000_000))

    async def restore_inputs(self, workspace, store, thread_id, names):
        from .files import inputs
        files = inputs(store,thread_id,names)
        if not files: return
        # Reuse the no-follow project file importer for paths controlled by the broker.
        script = "import json,sys,base64,os; from pathlib import Path\np=Path('/home/sandbox/project/chat-inputs'); p.mkdir(exist_ok=True)\nfd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)\nfor e in json.load(sys.stdin):\n f=os.open(e['name'],os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600,dir_fd=fd)\n with os.fdopen(f,'wb') as out: out.write(base64.b64decode(e['data'],validate=True))\nos.close(fd)"
        await self.invoke(workspace,script,files)


class AzureProjects(AzureWorkspaces):
    def __init__(self): super().__init__('headless')

    async def workspace(self, thread, store, context):
        project = store.ensure_project(thread,context['owner'])
        wid = thread.metadata.get('workspace_id')
        if wid: return await self.runtime.start(wid)
        ws = await self.runtime.create('headless','ai-'+project['id'][-16:],owner=context['owner'])
        thread.metadata['workspace_id'] = ws['id']
        thread.metadata['compute_provider'] = 'azure'
        await store.save_thread(thread,context)
        return ws

    async def run(self, thread, prompt, mode, run, store, context, input_files=None):
        project = store.ensure_project(thread,context['owner'])
        run.update(project_id=project['id'],status='queued'); store.save_run(run)
        async with self.project_locks.setdefault(project['id'],asyncio.Lock()), self.slots:
            from .azure_agent import run_agent
            return await run_agent(self,thread,prompt,mode,run,store,context,input_files or [])


class AzureDeveloper(AzureWorkspaces):
    def __init__(self): super().__init__('developer')

    def public(self, ws):
        from .workspace_usage import suggestion
        record=self.runtime.record(ws['id'])
        return {'id':ws['id'],'name':ws['name'],'status':ws['latest_build']['status'],'provider':'azure',
                'harness_status':self.harness.get(ws['id'],'Ready'),
                'suggested_compute':suggestion(record.get('usage',{}),record.get('compute_size','performance')),
                'last_used_at':self.runtime.record(ws['id']).get('last_opened_at',self.runtime.record(ws['id'])['created_at']),
                'compute_size':self.runtime.record(ws['id']).get('compute_size','performance'),
                'harness_error':self.setup_errors.get(ws['id']),
                'url':f'/api/developer/workspaces/{ws["id"]}/open', 'ide_url':f'/api/developer/workspaces/{ws["id"]}/open'}

    async def list(self): return [self.public(w) for w in await self.runtime.list('developer')]

    def lookup(self, wid):
        # Opening a known workspace does not need an inventory of its group.
        # start() still verifies remote readiness before execution or IDE access.
        from .identity import current_owner
        record=self.runtime.record(wid)
        if record['kind']!='developer' or record['state']=='deleted' or record.get('warm') or record.get('owner')!=current_owner.get():
            raise ValueError('Workspace not found')
        return self.public(self.runtime.workspace(record))

    async def start(self, name, *, owner=None, compute_size='light'):
        from .titles import clean_title
        from .identity import current_owner
        name=clean_title(name)
        if compute_size not in ('light','balanced','performance'):raise ValueError('Unknown compute size')
        ws=await self.runtime.create('developer','ws-'+uuid.uuid4().hex[:20],owner=owner or current_owner.get(),compute_size=compute_size)
        record=self.runtime.record(ws['id']);record['display_name']=name;record['last_opened_at']=time.time();self.runtime.save(record)
        ws['name']=name
        self.touched[ws['id']]=time.time();self.configure(ws['id'],name)
        return self.public(ws)

    async def prepare(self, workspace, *, editor=True):
        await self.runtime.start(workspace['id'])
        self.touched[workspace['id']] = time.time()
        self.runtime.touch(workspace['id'])
        from .activity import background_activity
        if not background_activity.get():
            record=self.runtime.record(workspace['id']);record['last_opened_at']=time.time();self.runtime.save(record)
            if editor:await self.runtime.editor_profiles.for_open(record)
        if editor and self.configured_until.get(workspace['id'], 0) < time.time():
            self.configure(workspace['id'], workspace['name'])
            # The editor is already healthy. Harness setup has its own visible
            # status and must not hold the editor open request behind npm work.

    async def ide(self, workspace):
        from .previews import previews
        return await previews.azure_app(workspace,port=13337,ide=True)

    async def delete(self, wid):
        if self.runtime.record(wid)['kind'] != 'developer': raise LookupError('Workspace not found')
        await self.runtime.stop(wid,delete=True)
        return {'id':wid,'status':'deleted'}

    def configure(self, wid, name):
        if wid in self.tasks and not self.tasks[wid].done(): return
        self.harness[wid] = 'Preparing coding tools…'
        self.setup_errors.pop(wid, None)
        async def configure():
            try:
                from .azure_developer import configure as setup
                await setup(self,await self.runtime.get(wid))
                self.harness[wid] = 'Ready'
                self.configured_until[wid] = min(time.time()+3300, self.runtime.record(wid)['lease_until'])
            except Exception as error:
                self.harness[wid] = 'Coding tools setup needs retry'; self.setup_errors[wid] = str(error)
                self.runtime.telemetry.event('developer',wid,'harness_setup_failed',error=str(error))
        self.tasks[wid] = asyncio.create_task(configure())

    async def activity(self, wid): return self.touched.get(wid,0)

    async def maintain_credentials(self):
        while True:
            for wid, until in list(self.capability_until.items()):
                if until < time.time()+300 and time.time()-self.touched.get(wid,0)<600:
                    try:
                        from .capabilities import issue
                        payload = issue(wid)
                        await self.invoke(await self.runtime.get(wid),(ROOT/'sandbox/rotate_capability.py').read_text(),payload)
                        self.capability_until[wid] = payload['expires']; self.renewal_error = None
                    except Exception: self.renewal_error = 'Azure developer credential renewal needs retry'
            await asyncio.sleep(30)


class AzureQuick:
    provider = 'azure'
    def __init__(self):
        from .scaling import WarmPolicy
        self.runtime = runtime(); self.ready = False; self.error = None
        self.slots = asyncio.Semaphore(self.runtime.profile('quick')['active_limit']); self.queued = 0; self.executing = 0
        self.policy = WarmPolicy(0,0,600,minimum=0); self.refill = asyncio.Event()

    async def pool(self):
        self.runtime.configured()
        await self.runtime.transport.call('list',self.runtime.profile('quick')['group'])
        self.ready = True
        return [r for r in self.runtime.records('quick') if r.get('warm') and r['state']=='running']

    def status(self):
        return {'provider':'azure','queued':self.queued,'executing':self.executing,'ready':self.runtime.warm.status('quick')['ready'],'target_reserve':self.runtime.warm.status('quick')['target'],'minimum_reserve':0,
                'max_concurrency':self.runtime.profile('quick')['active_limit'],'max_pods':self.runtime.profile('quick')['retained_limit'],'idle_seconds':600,'warm_hits':self.runtime.warm.hits,'cold_misses':self.runtime.warm.misses,'refill_seconds':0,
                'error':self.runtime.error,'budget':self.runtime.budget.status()}

    async def maintain(self): await asyncio.gather(self.runtime.maintain(),self.runtime.warm.maintain())

    async def quick(self, code, run, store, input_files=None):
        from .files import inputs
        from . import checkpoints
        self.queued += 1; started = time.monotonic(); entered = False; ws = None
        try:
            async with self.slots:
                entered = True; self.queued -= 1; self.executing += 1
                run['timings'] = {'queue_seconds':time.monotonic()-started}
                try:
                    checkpoint_files = checkpoints.load(run['thread_id'])
                    if not (checkpoints.directory(run['thread_id'])/'latest.json').exists() and self.runtime.storage.enabled:
                        saved = await self.runtime.storage.load('chats',run['thread_id'])
                        if saved: checkpoint_files = checkpoints.validate(saved['files'])
                    ws = await self.runtime.create('quick','quick-'+uuid.uuid4().hex[:12],disposable=True)
                    run.update(pod=ws['name'],status='running',compute_provider='azure'); store.save_run(run)
                    response = await self.runtime.execute(ws['id'],['python','/opt/lab/quick.py'],cwd='/workspace',
                        stdin=json.dumps({'code':code,'files':inputs(store,run['thread_id'],input_files or []),'checkpoint':checkpoint_files}),
                        timeout=value('QUICK_RUN_SECONDS')+15,maximum=value('ARTIFACT_MAX_TOTAL_BYTES')*4+1_000_000)
                    if response['exit_code']: raise RuntimeError('Quick execution failed: '+response.get('stderr','')[:300])
                    result = json.loads(response['stdout']); checkpoint = result.pop('checkpoint',None)
                    if checkpoint is not None:
                        run['checkpoint'] = checkpoints.save(run['thread_id'],run['id'],checkpoint); result['checkpoint'] = run['checkpoint']
                        await self.runtime.storage.save('chats',run['thread_id'],{'files':checkpoints.validate(checkpoint.get('files',[])),'truncated':bool(checkpoint.get('truncated'))})
                    result.setdefault('artifacts',[]).insert(0,{'name':'quick-source.py','data':base64.b64encode(code.encode()).decode()})
                    return result
                finally:
                    if ws: await self.runtime.stop(ws['id'],delete=True)
                    self.executing -= 1
                    run['timings']['total_seconds'] = time.monotonic()-started; store.save_run(run)
        finally:
            if not entered: self.queued -= 1
