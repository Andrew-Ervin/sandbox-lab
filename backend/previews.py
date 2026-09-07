"""Bounded local preview leases; expired servers and port forwards are reclaimed."""
import asyncio,os,socket,time,mimetypes
from urllib.parse import urlsplit
import uvicorn
from . import preview
from .config import ROOT,STATE,CODER_URL

class Previews:
    def __init__(self):
        self.resources={};self.app_ports={};self.artifact_ports={};self.lock=asyncio.Lock()
        self.idle_seconds=float(os.getenv('PREVIEW_IDLE_SECONDS','120'))
    def reserve(self):
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);sock.setblocking(False);return sock
    async def expose(self,target,process=None,log=None):
        sock=self.reserve();port=sock.getsockname()[1]
        preview.targets[port]={**target,'expires':time.time()+self.idle_seconds}
        server=uvicorn.Server(uvicorn.Config(preview.app,host='127.0.0.1',port=port,log_level='error',access_log=False,timeout_graceful_shutdown=2))
        self.resources[port]={'server':server,'task':asyncio.create_task(server.serve(sockets=[sock])),'process':process,'log':log}
        return f'http://127.0.0.1:{port}/'
    def renew(self,url):
        port=urlsplit(url).port;resource=self.resources.get(port);target=preview.targets.get(port)
        if not resource or not target or resource['task'].done(): return False
        if resource['process'] and resource['process'].returncode is not None: return False
        target['expires']=time.time()+self.idle_seconds;return True
    def active_workspaces(self):
        return {t['workspace_id'] for t in preview.targets.values() if t.get('workspace_id') and t['expires']>time.time()}
    async def remove_workspace(self,wid):
        async with self.lock:
            for port,target in list(preview.targets.items()):
                if target.get('workspace_id')==wid:await self.remove(port)
    async def remove(self,port):
        resource=self.resources.pop(port,None);preview.targets.pop(port,None)
        self.app_ports={k:v for k,v in self.app_ports.items() if urlsplit(v).port!=port}
        self.artifact_ports={k:v for k,v in self.artifact_ports.items() if urlsplit(v).port!=port}
        if not resource: return
        resource['server'].should_exit=True
        try: await asyncio.wait_for(asyncio.shield(resource['task']),4)
        except asyncio.TimeoutError: resource['task'].cancel()
        await asyncio.gather(resource['task'],return_exceptions=True)
        process=resource['process']
        if process and process.returncode is None:
            process.terminate()
            try: await asyncio.wait_for(process.wait(),3)
            except asyncio.TimeoutError: process.kill();await process.wait()
        if resource['log']: resource['log'].close()
    async def artifact(self,path):
        media=mimetypes.guess_type(path.name)[0]
        media=media or 'application/octet-stream'
        async with self.lock:
            old=self.artifact_ports.get(str(path))
            if old and self.renew(old): return old
            if old: await self.remove(urlsplit(old).port)
            url=await self.expose({'kind':'artifact','path':path,'media_type':media});self.artifact_ports[str(path)]=url;return url
    async def document(self,key,name,content):
        async with self.lock:
            cache_key='document:'+key
            old=self.artifact_ports.get(cache_key)
            if old and self.renew(old):return old
            if old:await self.remove(urlsplit(old).port)
            url=await self.expose({'kind':'document','name':name,'content':content,'media_type':'application/json'})
            self.artifact_ports[cache_key]=url
            return url
    async def app(self,workspace,settings,coder_url=CODER_URL):
        async with self.lock:
            key=(coder_url,workspace['id']);old=self.app_ports.get(key)
            if old and self.renew(old): return old
            if old: await self.remove(urlsplit(old).port)
            sock=self.reserve();upstream=sock.getsockname()[1];sock.close()
            env=dict(os.environ,CODER_URL=coder_url,CODER_SESSION_TOKEN=settings['token'],CODER_CONFIG_DIR=str(STATE/'coder-service-cli'),CODER_USE_KEYRING='false')
            log=open(STATE/f'preview-{workspace["id"]}.log','ab');process=None
            try:
                process=await asyncio.create_subprocess_exec(str(ROOT/'.local/bin/coder'),'port-forward',workspace['name'],'--tcp',f'127.0.0.1:{upstream}:3000','--disable-autostart',env=env,stdout=log,stderr=log)
                for _ in range(100):
                    if process.returncode is not None: raise RuntimeError('Workspace preview connection failed')
                    try:
                        _,writer=await asyncio.open_connection('127.0.0.1',upstream);writer.close();await writer.wait_closed();break
                    except OSError: await asyncio.sleep(.1)
                else: raise RuntimeError('Workspace preview connection timed out')
                url=await self.expose({'kind':'app','upstream_port':upstream,'workspace_id':workspace['id']},process,log)
                self.app_ports[key]=url;return url
            except BaseException:
                if process and process.returncode is None: process.terminate();await process.wait()
                log.close();raise
    async def reap(self):
        async with self.lock:
            expired=[port for port,resource in list(self.resources.items()) if preview.targets.get(port,{}).get('expires',0)<=time.time() or resource['task'].done()]
            await asyncio.gather(*(self.remove(port) for port in expired))
    async def maintain(self):
        while True:
            await asyncio.sleep(15);await self.reap()
    async def close(self):
        async with self.lock:
            await asyncio.gather(*(self.remove(port) for port in list(self.resources)))
previews=Previews()
