"""Bounded local preview leases; expired servers and port forwards are reclaimed."""
import asyncio,json,os,socket,time,mimetypes,secrets
from urllib.parse import urlsplit
import uvicorn
from contextlib import nullcontext

class PreviewServer(uvicorn.Server):
    # Embedded listeners must not replace the main broker signal handlers.
    def capture_signals(self):
        return nullcontext()

from . import preview
from .config import ROOT,STATE

class Previews:
    def __init__(self):
        self.resources={};self.app_ports={};self.artifact_ports={};self.app_sources={};self.lock=asyncio.Lock()
        self.idle_seconds=float(os.getenv('PREVIEW_IDLE_SECONDS','120'))
    def reserve(self,target=None):
        # A unique stable IDE origin retains folder-scoped browser trust. Never
        # reuse another workstation's registered origin, even after its deletion.
        path=STATE/'preview-origins.json'
        origins=json.loads(path.read_text()) if path.exists() else {}
        key=target.get('workspace_id') if target and target.get('kind')=='ide' else None
        port=origins.get(key,0) if key else 0
        if type(port) is not int or port and not 1024<=port<=65535:raise RuntimeError('Invalid saved preview origin')
        sock=socket.socket()
        try:
            sock.bind(('127.0.0.1',port))
            while not port and sock.getsockname()[1] in origins.values():
                sock.close();sock=socket.socket();sock.bind(('127.0.0.1',0))
        except OSError:
            sock.close()
            raise RuntimeError('The saved workstation preview port is occupied. Close its previous preview server and reopen the workstation.')
        if key and not port:
            origins[key]=sock.getsockname()[1];path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(origins));path.chmod(0o600)
        sock.listen(128);sock.setblocking(False);return sock
    async def expose(self,target,process=None,log=None):
        from .identity import current_owner
        if not target.get('owner'):target['owner']=current_owner.get()
        sock=self.reserve(target);port=sock.getsockname()[1]
        target={**target}
        if target.get('kind')=='app':target['capability']=secrets.token_urlsafe(24)
        preview.targets[port]={**target,'expires':time.time()+(600 if target.get('kind')=='ide' else self.idle_seconds)}
        server=PreviewServer(uvicorn.Config(preview.app,host='127.0.0.1',port=port,log_level='error',access_log=False,timeout_graceful_shutdown=2))
        self.resources[port]={'server':server,'task':asyncio.create_task(server.serve(sockets=[sock])),'process':process,'log':log}
        suffix=f'/_lab/{target["capability"]}/' if target.get('kind')=='app' else '/'
        return f'http://127.0.0.1:{port}{suffix}'
    def renew(self,url):
        port=urlsplit(url).port;resource=self.resources.get(port);target=preview.targets.get(port)
        if not resource or not target or resource['task'].done(): return False
        if resource['process'] and resource['process'].returncode is not None: return False
        target['expires']=time.time()+(600 if target.get('kind')=='ide' else self.idle_seconds);return True
    def active_workspaces(self):
        return {t['workspace_id'] for t in preview.targets.values() if t.get('workspace_id') and t['expires']>time.time()}
    def renew_workspace(self,wid):
        return any([self.renew(f'http://127.0.0.1:{port}/') for port,target in list(preview.targets.items()) if target.get('workspace_id')==wid and target.get('kind')=='ide'])
    async def remove_workspace(self,wid):
        self.app_sources.pop(wid,None)
        async with self.lock:
            for port,target in list(preview.targets.items()):
                if target.get('workspace_id')==wid:await self.remove(port)
    async def remove(self,port):
        resource=self.resources.pop(port,None);target=preview.targets.pop(port,None)
        if target and target.get('http_client'):await target['http_client'].aclose()
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
        if resource.get('tunnel'):
            resource['tunnel'].close();await resource['tunnel'].wait_closed()
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
    async def app(self,workspace,settings=None,**kwargs):
        url=await self.azure_app(workspace)
        if 'source_path' in kwargs:self.app_sources[workspace['id']]=kwargs['source_path']
        return url
    async def ready_app(self,wid,source_path=None):
        """Probe the already-running app through its fixed private tunnel."""
        if wid not in self.app_sources or self.app_sources[wid]!=source_path:return None
        import httpx
        from .azure_runtime import runtime
        control=runtime();record=control.record(wid)
        if record['state']!='running' or record.get('lease_until',0)<time.time()+30:return None
        try:
            url=await self.azure_app({'id':wid})
            target=preview.targets[urlsplit(url).port]
            async with httpx.AsyncClient(timeout=2,trust_env=False) as client:
                async with client.stream('GET',f'http://127.0.0.1:{target["upstream_port"]}/') as response:
                    if response.status_code>=400:return None
            control.touch(wid);control.warm.demand(record['kind']);return url
        except (httpx.HTTPError,RuntimeError,OSError):return None
    async def azure_app(self,workspace,port=3000,ide=False):
        from .azure_runtime import runtime
        from .azure_services import tunnel
        async with self.lock:
            key=('azure',workspace['id'],port);old=self.app_ports.get(key)
            if old and self.renew(old):return old
            if old:await self.remove(urlsplit(old).port)
            control=runtime();record=control.record(workspace['id'])
            if record['state']!='running' or record.get('lease_until',0)<=time.time():raise RuntimeError('Azure workspace is asleep. Reopen it to resume.')
            server=await asyncio.start_server(lambda r,w:tunnel(control,workspace['id'],port,r,w),'127.0.0.1',0)
            try:
                url=await self.expose({'kind':'ide' if ide else 'app','upstream_port':server.sockets[0].getsockname()[1],'workspace_id':workspace['id'],'owner':record.get('owner')})
                self.resources[urlsplit(url).port]['tunnel']=server;self.app_ports[key]=url;return url
            except BaseException:
                server.close();await server.wait_closed();raise
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
