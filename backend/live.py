"""Host control-plane status reads. Never return pod specs or pass credentials to pods."""
import asyncio,time
from .config import STATE


def runtime(workspace_id,build_status,live,namespace):
    if build_status=='deleting':return 'deleting'
    if namespace in live['unavailable_namespaces']:return 'unknown'
    pod=next((p for p in live['pods'] if p['namespace']==namespace and p['workspace_id']==workspace_id),None)
    if pod:return pod['state']
    if build_status in ['pending','starting','stopping','failed','canceled']:return build_status
    return 'stopped'

class AzureLiveContainers:
    def __init__(self):self.expires=0;self.value=None;self.lock=asyncio.Lock()
    async def get(self):
        from .azure_runtime import runtime
        if self.value and time.monotonic()<self.expires:return self.value
        async with self.lock:
            if self.value and time.monotonic()<self.expires:return self.value
            control=runtime();pods=[];errors=[]
            for kind,namespace in [('quick','lab-sandboxes'),('headless','lab-agents'),('developer','lab-dev')]:
                try:
                    for ws in await control.list(kind):
                        state=ws['latest_build']['status']
                        pods.append({'namespace':namespace,'group':control.profile(kind)['group'],'name':ws['name'],'state':state,
                                     'ready':state=='running','restarts':0,'reason':'','workspace_id':ws['id'],'pool_state':None,'provider':'azure'})
                except Exception:errors.append(namespace)
            self.value={'provider':'azure','observed_at':time.time(),'pods':pods,'unavailable_namespaces':errors}
            self.expires=time.monotonic()+10;return self.value

live_containers=AzureLiveContainers()
