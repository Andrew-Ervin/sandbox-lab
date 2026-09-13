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
    def __init__(self):self.expires=0;self.value=None;self.task=None
    async def get(self):
        from .azure_runtime import runtime
        control=runtime()
        if time.monotonic()>=self.expires and (self.task is None or self.task.done()):
            self.task=asyncio.create_task(self.refresh(control))
        if self.value and time.monotonic()<self.expires:return self.value
        # Browsing is local and immediate; opening still checks Azure readiness.
        namespaces={'quick':'lab-sandboxes','headless':'lab-agents','developer':'lab-dev'}
        pods=[{'namespace':namespaces[r['kind']],'group':control.profile(r['kind'])['group'],
               'name':r.get('display_name',r['name']),'state':r['state'],'ready':False,
               'restarts':0,'reason':'Awaiting cloud observation','workspace_id':r['id'],'pool_state':None,'provider':'azure'}
              for r in control.records() if r['state']!='deleted' and not r.get('warm')]
        return {'provider':'azure','observed_at':None,'pods':pods,'unavailable_namespaces':[],'stale':True}

    async def refresh(self,control):
        kinds=[('quick','lab-sandboxes'),('headless','lab-agents'),('developer','lab-dev')]
        results=await asyncio.gather(*(control.list(kind) for kind,_ in kinds),return_exceptions=True)
        pods=[];errors=[]
        for (kind,namespace),result in zip(kinds,results):
            if isinstance(result,BaseException):errors.append(namespace);continue
            for ws in result:
                state=ws['latest_build']['status']
                pods.append({'namespace':namespace,'group':control.profile(kind)['group'],'name':ws['name'],'state':state,
                             'ready':state=='running','restarts':0,'reason':'','workspace_id':ws['id'],'pool_state':None,'provider':'azure'})
        self.value={'provider':'azure','observed_at':time.time(),'pods':pods,'unavailable_namespaces':errors,'stale':False}
        self.expires=time.monotonic()+10;return self.value

live_containers=AzureLiveContainers()
