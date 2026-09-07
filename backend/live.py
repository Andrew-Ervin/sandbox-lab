"""Host control-plane status reads. Never return pod specs or pass credentials to pods."""
import asyncio,time
from kubernetes import client,config
from .config import STATE

NAMESPACES=('lab-sandboxes','lab-agents','lab-dev','lab-control','coder','coder-ai')
class LiveContainers:
    def __init__(self):self.expires=0;self.value=None;self.lock=asyncio.Lock()
    async def read(self,namespace):
        def invoke():
            cfg=client.Configuration();config.load_kube_config(config_file=str(STATE/'kubeconfig'),client_configuration=cfg)
            api=client.CoreV1Api(client.ApiClient(cfg))
            try:return api.list_namespaced_pod(namespace,_request_timeout=5)
            finally:api.api_client.close()
        return await asyncio.to_thread(invoke)
    async def get(self):
        if self.value and time.monotonic()<self.expires:return self.value
        async with self.lock:
            if self.value and time.monotonic()<self.expires:return self.value
            result=await asyncio.gather(*(self.read(ns) for ns in NAMESPACES),return_exceptions=True)
            pods=[];errors=[]
            for ns,response in zip(NAMESPACES,result):
                if isinstance(response,BaseException):errors.append(ns);continue
                for pod in response.items:
                    statuses=pod.status.container_statuses or []
                    ready=bool(statuses) and all(c.ready for c in statuses)
                    state='stopping' if pod.metadata.deletion_timestamp else pod.status.phase.lower()
                    if state=='running' and not ready:state='starting'
                    reasons=[c.state.waiting.reason for c in statuses if c.state and c.state.waiting]
                    pods.append({'namespace':ns,'name':pod.metadata.name,'state':state,'ready':ready,
                                 'restarts':sum(c.restart_count for c in statuses),'reason':', '.join(reasons),
                                 'workspace_id':pod.metadata.name.removeprefix('ws-') if pod.metadata.name.startswith('ws-') else None,
                                 'pool_state':(pod.metadata.labels or {}).get('lab/state')})
            self.value={'observed_at':time.time(),'pods':pods,'unavailable_namespaces':errors};self.expires=time.monotonic()+3
            return self.value

def runtime(workspace_id,build_status,live,namespace):
    if build_status=='deleting':return 'deleting'
    if namespace in live['unavailable_namespaces']:return 'unknown'
    pod=next((p for p in live['pods'] if p['namespace']==namespace and p['workspace_id']==workspace_id),None)
    if pod:return pod['state']
    if build_status in ['pending','starting','stopping','failed','canceled']:return build_status
    return 'stopped'

live_containers=LiveContainers()
