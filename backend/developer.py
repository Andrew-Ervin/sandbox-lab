"""Human-only workspace controls. This adapter is never exposed as an AI tool."""
import asyncio, json, re, time, os
import httpx
from .config import STATE, ROOT
from .activity import Activity

class DeveloperWorkspaces:
    def __init__(self): self.lock=asyncio.Lock(); self.token=None; self.tasks={}; self.harness={}; self.touched=Activity('developer'); self.configured_until={}; self.setup_errors={};self.login_lock=asyncio.Lock();self.capability_until={};self.renewal_error=None
    async def api(self,method,path,**kwargs):
        async with httpx.AsyncClient(base_url='http://127.0.0.1:7080',trust_env=False,timeout=30) as c:
            for attempt in range(2):
                if not self.token:
                    async with self.login_lock:
                        if not self.token:
                            cred=json.loads((STATE/'coder-admin.json').read_text())
                            auth=await c.post('/api/v2/users/login',json={'email':cred['email'],'password':cred['password']})
                            auth.raise_for_status();self.token=auth.json()['session_token']
                sent_token=self.token
                r=await c.request(method,path,headers={'Coder-Session-Token':sent_token},**kwargs)
                if r.status_code==401 and attempt==0:
                    if self.token==sent_token:self.token=None
                    continue
                r.raise_for_status()
                return r.json() if r.content else {}
    def public(self,ws):
        return {'id':ws['id'],'name':ws['name'],'status':ws['latest_build']['status'],'harness_status':self.harness.get(ws['id'],'Available to configure'),
                'url':f'http://127.0.0.1:7080/@{ws["owner_name"]}/{ws["name"]}',
                'ide_url':f'http://127.0.0.1:7080/@{ws["owner_name"]}/{ws["name"]}/apps/vscode/'}
    async def list(self):
        result=await self.api('GET','/api/v2/workspaces',params={'q':'owner:me'})
        return [self.public(w) for w in result.get('workspaces',[]) if not w.get('deleted')]
    async def delete(self,workspace_id):
        async with self.lock:
            workspace=next((w for w in await self.list() if w['id']==workspace_id),None)
            if not workspace: raise LookupError('Workspace not found')
            if workspace['status'] in ('starting','stopping','pending','canceling'):
                raise ValueError('Wait for the current workspace operation to finish before deleting.')
            if workspace['status']!='deleting':
                await self.api('POST',f'/api/v2/workspaces/{workspace_id}/builds',json={'transition':'delete'})
            task=self.tasks.pop(workspace_id,None)
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
            self.configured_until.pop(workspace_id,None)
            self.capability_until.pop(workspace_id,None)
            self.harness.pop(workspace_id,None)
            return {'id':workspace_id,'status':'deleting'}

    async def activity(self,workspace_id):
        # Fixed read of an untrusted activity marker, never commands from a workspace.
        if not re.fullmatch('[a-f0-9-]{36}',workspace_id):return 0
        script="import os,json; p='/home/sandbox/.config/lab/activity.json'; f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK); d=json.loads(os.read(f,1024)); print(float(d.get('at',0)))"
        p=await asyncio.create_subprocess_exec('kubectl','--kubeconfig',str(STATE/'kubeconfig'),'-n','lab-dev','exec','ws-'+workspace_id,'--','python','-c',script,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            out,_=await asyncio.wait_for(p.communicate(),5)
            used=min(time.time(),float(out)) if p.returncode==0 else 0
            if used>self.touched.get(workspace_id,0):self.touched[workspace_id]=used
            return used
        except (ValueError,asyncio.TimeoutError):return 0
        finally:
            if p.returncode is None:p.kill();await p.wait()

    async def start(self,name):
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,27}',name): raise ValueError('Use a lowercase workspace name with letters, numbers and dashes (1–28 characters).')
        async with self.lock:
            existing=next((w for w in await self.list() if w['name']==name),None)
            if existing:
                ws=await self.api('GET','/api/v2/workspaces/'+existing['id'])
                if ws['latest_build']['status'] in ['stopped','failed','canceled']:
                    template=await self.api('GET','/api/v2/templates/'+ws['template_id'])
                    await self.api('POST',f'/api/v2/workspaces/{ws["id"]}/builds',json={'transition':'start','template_version_id':template['active_version_id']})
                    ws=await self.api('GET','/api/v2/workspaces/'+ws['id'])
            else:
                org=json.loads((STATE/'coder-org.json').read_text())
                templates=await self.api('GET',f'/api/v2/organizations/{org["id"]}/templates')
                template=next(t for t in templates if t['name']=='developer')
                ws=await self.api('POST',f'/api/v2/organizations/{org["id"]}/members/me/workspaces',json={'name':name,'template_id':template['id'],'ttl_ms':int(float(os.getenv('DEVELOPER_IDLE_SECONDS','600'))*1000)})
            self.touched[ws['id']]=time.time()
            self.configure(ws['id'],ws['name'])
            return self.public(ws)
    async def prepare(self,workspace):
        self.touched[workspace['id']]=time.time()
        task=self.tasks.get(workspace['id'])
        if not task or task.done():
            if self.configured_until.get(workspace['id'],0)>=time.time():return
            self.configure(workspace['id'],workspace['name'])
            task=self.tasks[workspace['id']]
        await task
        if self.configured_until.get(workspace['id'],0)<time.time():
            raise RuntimeError(self.setup_errors.get(workspace['id'],'Pi / Ori setup needs retry.'))

    def configure(self,workspace_id,name):
        if workspace_id in self.tasks and not self.tasks[workspace_id].done(): return
        self.harness[workspace_id]='Preparing Ori / Pi'
        self.setup_errors.pop(workspace_id,None)
        async def run():
            try:
                for _ in range(90):
                    ws=await self.api('GET','/api/v2/workspaces/'+workspace_id)
                    if ws['latest_build']['status'] in ('failed','canceled','stopped','deleted'):
                        raise RuntimeError('Workspace startup failed. Check its Coder build and available storage/compute quota, then retry.')
                    agents=[a for r in ws['latest_build'].get('resources',[]) for a in r.get('agents',[])]
                    if any(a['status']=='connected' for a in agents): break
                    await asyncio.sleep(2)
                else: raise RuntimeError('Workspace is not ready')
                proc=await asyncio.create_subprocess_exec(str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/configure_developer.py'),'--workspace',name,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                try:
                    await asyncio.wait_for(proc.communicate(),300)
                    if proc.returncode: raise RuntimeError('Harness setup failed')
                finally:
                    if proc.returncode is None: proc.kill(); await proc.wait()
                self.harness[workspace_id]='Pi through Ori · default agent'
                self.configured_until[workspace_id]=time.time()+3300
                self.capability_until[workspace_id]=time.time()+3500
            except Exception as exc:
                self.harness[workspace_id]='Setup needs retry — use Refresh Ori / Pi'
                self.setup_errors[workspace_id]=str(exc) if isinstance(exc,RuntimeError) else 'Workspace setup could not finish; retry opening it.'
        self.tasks[workspace_id]=asyncio.create_task(run())

    async def refresh_capability(self,wid):
        from .capabilities import issue
        payload=issue(wid)
        proc=await asyncio.create_subprocess_exec('kubectl','--kubeconfig',str(STATE/'kubeconfig'),'-n','lab-dev','exec','-i','ws-'+wid,'--','python','-I','-c',(ROOT/'sandbox/rotate_capability.py').read_text(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            await asyncio.wait_for(proc.communicate(json.dumps(payload).encode()),20)
            if proc.returncode:raise RuntimeError('Workspace credential renewal needs retry')
            self.capability_until[wid]=payload['expires']
        finally:
            if proc.returncode is None:proc.kill();await proc.wait()

    async def renew_active(self):
        from .limits import value
        workspaces=(await self.api('GET','/api/v2/workspaces',params={'q':'owner:me'}))['workspaces']
        failures=False
        for ws in workspaces:
            wid=ws['id']
            if ws.get('deleted') or ws['latest_build']['status']!='running':continue
            if wid in self.tasks and not self.tasks[wid].done():continue
            if self.capability_until.get(wid,0)>time.time()+value('WORKSPACE_TOKEN_RENEW_BEFORE_SECONDS'):continue
            try:
                used=self.touched.get(wid,0)
                if time.time()-used>=value('DEVELOPER_IDLE_SECONDS'):used=max(used,await self.activity(wid))
                if time.time()-used<value('DEVELOPER_IDLE_SECONDS'):
                    await self.refresh_capability(wid)
            except Exception:failures=True
        if failures:raise RuntimeError('One or more workspace credentials need retry')

    async def maintain_credentials(self):
        while True:
            try:await self.renew_active();self.renewal_error=None
            except Exception:self.renewal_error='Workspace credential renewal will retry. Existing scoped credentials keep their original expiry.'
            await asyncio.sleep(30)

developer=DeveloperWorkspaces()
