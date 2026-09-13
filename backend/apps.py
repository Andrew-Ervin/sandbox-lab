"""Click-driven workspace and app resume, independent of ChatKit/model execution."""
import asyncio,os,re,shlex,time
from urllib.parse import urlencode
from .config import ROOT,STATE

def developer_source_url(url,source_path):
    if not source_path:return url
    if not isinstance(source_path,str) or not re.fullmatch(r'\.lab/imports/transfer_[a-f0-9]{32}',source_path):
        raise ValueError('Invalid developer source folder')
    return url+'?'+urlencode({'folder':'/home/sandbox/project/'+source_path})
class AppLifecycle:
    def __init__(self):self.locks={}
    async def launch(self,workspace,token,url,source_path=None):
        from .azure_runtime import runtime
        from .limits import value
        developer_source_url('',source_path)
        script='import os; os.environ["APP_PACKAGE_RESTORE_SECONDS"]='+repr(str(value('APP_PACKAGE_RESTORE_SECONDS')))+'\n'+(ROOT/'sandbox/app_runtime.py').read_text()
        result=await runtime().execute(workspace['id'],['python','-I','-c',script,*([source_path] if source_path else [])],timeout=value('APP_PACKAGE_RESTORE_SECONDS')+140)
        if result['exit_code']:
            import json
            try:error=json.loads(result['stdout']).get('error')
            except (ValueError,AttributeError):error=None
            raise RuntimeError(error or 'Could not start the Azure app; inspect its launch recipe.')
        return
    async def ai(self,run,store,owner,headless,previews):
        async with self.locks.setdefault(run['workspace_id'],asyncio.Lock()):
            stopping=getattr(getattr(headless,'sessions',None),'stopping',set())
            # Opening immediately after Stop coding queues the wake until the
            # previous compute has actually stopped, without another chat turn.
            for _ in range(60):
                if run['workspace_id'] not in stopping:break
                await asyncio.sleep(1)
            else:raise ValueError('Workspace shutdown is taking longer than expected. Retry the preview shortly.')
            thread=await store.load_thread(run['thread_id'],{'owner':owner})
            if thread.metadata.get('workspace_id')!=run['workspace_id']:raise ValueError('App workspace ownership mismatch')
            project=store.project_for_thread(thread.id,owner)
            sync=(project or {}).get('workspace_sync') or {}
            source_path=sync.get('chat_source_path',sync.get('path') if sync.get('direction')=='to_chat' else None)
            if hasattr(previews,'ready_app'):
                ready=await previews.ready_app(run['workspace_id'],source_path)
                if ready:return ready
            ws=await headless.workspace(thread,store,{'owner':owner})
            headless.provisioning.add(ws['id']);headless.touched[ws['id']]=time.time()
            try:
                await self.launch(ws,headless.settings()['token'],'',source_path)
                return await previews.app(ws,headless.settings(),source_path=source_path)
            finally:headless.provisioning.discard(ws['id']);headless.touched[ws['id']]=time.time()
    async def human(self,workspace_id,developer,previews,ide=False,source_path=None):
        async with self.locks.setdefault(workspace_id,asyncio.Lock()):
            ws=developer.lookup(workspace_id)
            if not ws:raise ValueError('Workspace not found')
            if not ide and hasattr(previews,'ready_app'):
                ready=await previews.ready_app(workspace_id,source_path)
                if ready:return ready
            # Resume by immutable identity; display names can contain spaces or
            # change after the first exit and must never select a new sandbox.
            await developer.prepare(ws,editor=ide)
            developer.touched[workspace_id]=time.time()
            if ide:return await developer.ide(ws)
            await self.launch(ws,developer.token,'http://127.0.0.1:7080',source_path)
            return await previews.app(ws,{'token':developer.token},provider_url='http://127.0.0.1:7080',source_path=source_path)
apps=AppLifecycle()
