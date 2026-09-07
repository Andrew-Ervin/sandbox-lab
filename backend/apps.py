"""Click-driven workspace and app resume, independent of ChatKit/model execution."""
import asyncio,os,re,shlex,time
from urllib.parse import urlencode
from .config import ROOT,STATE,CODER_URL

def developer_source_url(url,source_path):
    if not source_path:return url
    if not isinstance(source_path,str) or not re.fullmatch(r'\.lab/imports/transfer_[a-f0-9]{32}',source_path):
        raise ValueError('Invalid developer source folder')
    return url+'?'+urlencode({'folder':'/home/sandbox/project/'+source_path})
class AppLifecycle:
    def __init__(self):self.locks={}
    async def launch(self,workspace,token,url,source_path=None):
        env=dict(os.environ,CODER_URL=url,CODER_SESSION_TOKEN=token,CODER_CONFIG_DIR=str(STATE/'coder-service-cli'),CODER_USE_KEYRING='false')
        developer_source_url('',source_path)
        script=(ROOT/'sandbox/app_runtime.py').read_text()
        from .limits import value
        command='python -I -c '+shlex.quote('import os; os.environ["APP_PACKAGE_RESTORE_SECONDS"]='+repr(str(value('APP_PACKAGE_RESTORE_SECONDS')))+'\n'+script)
        if source_path:command+=' '+shlex.quote(source_path)
        process=await asyncio.create_subprocess_exec(str(ROOT/'.local/bin/coder'),'ssh','--disable-autostart',workspace['name'],'--',command,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            out,_=await asyncio.wait_for(process.communicate(),value('APP_PACKAGE_RESTORE_SECONDS')+140)
            if process.returncode:
                import json
                try:error=json.loads(out).get('error')
                except Exception:error=None
                raise RuntimeError(error or 'Could not start this app. Retry or inspect its launch recipe.')
        finally:
            if process.returncode is None:process.kill();await process.wait()
    async def ai(self,run,store,owner,coder,previews):
        async with self.locks.setdefault(run['workspace_id'],asyncio.Lock()):
            stopping=getattr(getattr(coder,'sessions',None),'stopping',set())
            # Opening immediately after Stop coding queues the wake until the
            # previous compute has actually stopped, without another chat turn.
            for _ in range(60):
                if run['workspace_id'] not in stopping:break
                await asyncio.sleep(1)
            else:raise ValueError('Workspace shutdown is taking longer than expected. Retry the preview shortly.')
            thread=await store.load_thread(run['thread_id'],{'owner':owner})
            if thread.metadata.get('coder_workspace_id')!=run['workspace_id']:raise ValueError('App workspace ownership mismatch')
            ws=await coder.workspace(thread,store,{'owner':owner})
            coder.provisioning.add(ws['id']);coder.touched[ws['id']]=time.time()
            try:
                project=store.project_for_thread(thread.id,owner)
                sync=(project or {}).get('workspace_sync') or {}
                source_path=sync.get('chat_source_path',sync.get('path') if sync.get('direction')=='to_chat' else None)
                await self.launch(ws,coder.settings()['token'],CODER_URL,source_path)
                return await previews.app(ws,coder.settings())
            finally:coder.provisioning.discard(ws['id']);coder.touched[ws['id']]=time.time()
    async def human(self,workspace_id,developer,previews,ide=False,source_path=None):
        async with self.locks.setdefault(workspace_id,asyncio.Lock()):
            ws=next((w for w in await developer.list() if w['id']==workspace_id),None)
            if not ws:raise ValueError('Workspace not found')
            if ws['status']!='running':await developer.start(ws['name'])
            developer.touched[workspace_id]=time.time()
            for _ in range(90):
                full=await developer.api('GET','/api/v2/workspaces/'+workspace_id)
                agents=[a for r in full['latest_build'].get('resources',[]) for a in r.get('agents',[])]
                if full['latest_build']['status']=='running' and any(a['status']=='connected' for a in agents):break
                if full['latest_build']['status'] in ['failed','canceled']:raise RuntimeError('Workspace start failed. Retry from Developer workspaces.')
                await asyncio.sleep(2)
            else:raise RuntimeError('Workspace is still starting. Retry opening it shortly.')
            # prepare waits for Coder connectivity and configures model access.
            await developer.prepare(ws)
            if ide:return ws['ide_url']
            await self.launch(ws,developer.token,'http://127.0.0.1:7080',source_path)
            return await previews.app(ws,{'token':developer.token},coder_url='http://127.0.0.1:7080')
apps=AppLifecycle()
