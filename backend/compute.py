"""Kubernetes quick-compute pool. Every pod is consumed once and destroyed."""
import asyncio, json, time, uuid, subprocess, os, threading
from pathlib import Path
from kubernetes import client, config, watch
from .scaling import WarmPolicy
from .config import KUBECONFIG, NAMESPACE
from .files import inputs
from . import checkpoints

def pod_manifest(name):
    return {'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':NAMESPACE,'labels':{'lab/managed':'true','lab/mode':'quick','lab/state':'warm'}},'spec':{
      'restartPolicy':'Never','automountServiceAccountToken':False,'serviceAccountName':'unprivileged','activeDeadlineSeconds':1800,'terminationGracePeriodSeconds':0,
      'securityContext':{'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000,'fsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}},
      'containers':[{'name':'sandbox','image':'sandbox-lab/quick:local','imagePullPolicy':'Never','command':['sleep','infinity'],
        'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
        'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'768Mi','ephemeral-storage':'256Mi'}},
        'volumeMounts':[{'name':'work','mountPath':'/workspace'},{'name':'tmp','mountPath':'/tmp'},{'name':'home','mountPath':'/home/sandbox'}]}],
      'volumes':[{'name':'work','emptyDir':{'sizeLimit':'128Mi'}},{'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'64Mi'}},{'name':'home','emptyDir':{'sizeLimit':'16Mi'}}]}}
class Compute:
    def __init__(self):
        self.lock=asyncio.Lock();self.snapshot_lock=asyncio.Lock();self.ready=False
        self.refill=asyncio.Event();self.changed=asyncio.Event();self.cache={};self.initialized=False
        self.pool_size=max(0,int(os.getenv('WARM_POOL_SIZE','2')))
        self.max_concurrency=max(1,int(os.getenv('QUICK_CONCURRENCY','4')))
        self.max_pods=max(self.max_concurrency,int(os.getenv('QUICK_MAX_PODS','8')))
        self.policy=WarmPolicy(self.pool_size,min(self.max_pods,int(os.getenv('WARM_POOL_MAX','4'))),float(os.getenv('QUICK_IDLE_SECONDS','300')))
        self.slots=asyncio.Semaphore(self.max_concurrency)
        self.acquiring=0;self.queued=0;self.executing=0;self.leased=set();self.pending_created={}
        self.warm_hits=0;self.cold_misses=0;self.stop_watch=threading.Event();self.watcher=None
    def api(self):
        cfg=client.Configuration();config.load_kube_config(config_file=KUBECONFIG,client_configuration=cfg)
        return client.CoreV1Api(client.ApiClient(cfg))
    async def call(self,method,*args,**kw):
        def invoke():
            api=self.api()
            try: return getattr(api,method)(*args,**kw,_request_timeout=10)
            finally: api.api_client.close()
        return await asyncio.to_thread(invoke)
    async def snapshot(self):
        async with self.snapshot_lock:
            result=await self.call('list_namespaced_pod',NAMESPACE,label_selector='lab/mode=quick')
            self.cache={p.metadata.name:p for p in result.items};self.initialized=True;self.ready=True;self.changed.set()
            return getattr(getattr(result,'metadata',None),'resource_version',None)
    def is_ready(self,p):
        return p.status.phase=='Running' and all(c.ready for c in (getattr(p.status,'container_statuses',None) or []))
    async def pool(self):
        if not self.initialized: await self.snapshot()
        return [p for p in self.cache.values() if p.metadata.labels.get('lab/state')=='warm' and not p.metadata.deletion_timestamp and self.is_ready(p)]
    def event(self,event):
        p=event.get('object')
        if not getattr(p,'metadata',None): return
        if event['type']=='DELETED': self.cache.pop(p.metadata.name,None)
        else:
            self.cache[p.metadata.name]=p
            if self.is_ready(p) and p.metadata.name in self.pending_created:
                self.policy.observe_refill(time.monotonic()-self.pending_created.pop(p.metadata.name))
        self.changed.set();self.refill.set()
    async def observe(self):
        loop=asyncio.get_running_loop()
        while not self.stop_watch.is_set():
            try:
                version=await self.snapshot()
                def stream():
                    api=self.api();self.watcher=watch.Watch()
                    try:
                        for event in self.watcher.stream(api.list_namespaced_pod,NAMESPACE,label_selector='lab/mode=quick',resource_version=version,timeout_seconds=5,_request_timeout=(5,10)):
                            if self.stop_watch.is_set(): break
                            loop.call_soon_threadsafe(self.event,event)
                    finally: self.watcher.stop();api.api_client.close()
                await asyncio.to_thread(stream)
            except Exception:
                self.ready=False
                if not self.stop_watch.is_set(): await asyncio.sleep(1)
    async def retire(self,p):
        # CAS the warm label before deleting: another broker cannot claim it in between.
        try:
            await self.call('patch_namespaced_pod',p.metadata.name,NAMESPACE,{'metadata':{'resourceVersion':p.metadata.resource_version,'labels':{'lab/state':'retiring'}}})
            await self.call('delete_namespaced_pod',p.metadata.name,NAMESPACE)
            self.cache.pop(p.metadata.name,None);self.pending_created.pop(p.metadata.name,None)
        except client.exceptions.ApiException as exc:
            if exc.status not in [404,409]: raise
    async def replenish(self):
        if not self.initialized: await self.snapshot()
        async with self.lock:
            pods=[p for p in self.cache.values() if not p.metadata.deletion_timestamp]
            for p in pods:
                if p.status.phase in ['Failed','Succeeded'] or p.metadata.labels.get('lab/state')=='retiring':
                    try: await self.call('delete_namespaced_pod',p.metadata.name,NAMESPACE)
                    except client.exceptions.ApiException as exc:
                        if exc.status!=404: raise
                    self.cache.pop(p.metadata.name,None)
            pods=[p for p in self.cache.values() if not p.metadata.deletion_timestamp and p.status.phase in ['Pending','Running']]
            live=[p for p in pods if p.metadata.labels.get('lab/state')=='warm']
            occupied=len(pods)-len(live)
            self.policy.base=self.pool_size
            spare=self.policy.reserve(self.executing+self.queued+self.acquiring)
            target=min(max(0,self.max_pods-occupied),self.acquiring+spare)
            # Scale down unclaimed capacity only. Claimed pods belong to their running jobs.
            for p in live[target:]: await self.retire(p)
            for _ in range(max(0,target-len(live))):
                name='quick-'+uuid.uuid4().hex[:12]
                p=await self.call('create_namespaced_pod',NAMESPACE,pod_manifest(name))
                if p: self.cache[name]=p
                self.pending_created[name]=time.monotonic()
        self.ready=True
    async def maintain(self):
        self.stop_watch.clear();observer=asyncio.create_task(self.observe())
        try:
            while True:
                self.refill.clear()
                try: await self.replenish()
                except Exception: self.ready=False
                try: await asyncio.wait_for(self.refill.wait(),5)
                except asyncio.TimeoutError: pass
        finally:
            self.stop_watch.set()
            if self.watcher: self.watcher.stop()
            await asyncio.gather(observer,return_exceptions=True)
    async def acquire(self):
        self.acquiring+=1;self.policy.arrival();self.refill.set();deadline=time.monotonic()+60;first=True
        try:
            while time.monotonic()<deadline:
                self.changed.clear()
                async with self.lock:
                    available=await self.pool()
                    if first:
                        if available: self.warm_hits+=1
                        else: self.cold_misses+=1
                        first=False
                    if available:
                        p=available[0];name=p.metadata.name
                        try:
                            updated=await self.call('patch_namespaced_pod',name,NAMESPACE,{'metadata':{'resourceVersion':p.metadata.resource_version,'labels':{'lab/state':'leased'}}})
                            if updated: self.cache[name]=updated
                            else: p.metadata.labels['lab/state']='leased'
                            self.leased.add(name);self.refill.set();return name
                        except client.exceptions.ApiException as exc:
                            if exc.status not in [404,409]: raise
                await self.replenish()
                try: await asyncio.wait_for(self.changed.wait(),min(2,max(.01,deadline-time.monotonic())))
                except asyncio.TimeoutError: await self.snapshot()
            raise RuntimeError('No ready compute pod after 60 seconds; local capacity is exhausted.')
        finally: self.acquiring-=1;self.refill.set()
    def status(self):
        return {'queued':self.queued,'executing':self.executing,'ready':sum(p.metadata.labels.get('lab/state')=='warm' and self.is_ready(p) and not p.metadata.deletion_timestamp for p in self.cache.values()),'target_reserve':self.policy.reserve(self.executing+self.queued+self.acquiring),'max_concurrency':self.max_concurrency,'max_pods':self.max_pods,'idle_seconds':self.policy.idle_seconds,'warm_hits':self.warm_hits,'cold_misses':self.cold_misses,'refill_seconds':round(self.policy.refill_seconds,3)}
    async def execute(self, name, command, data=None, timeout=45, max_bytes=46_000_000):
        argv=['kubectl','--kubeconfig',KUBECONFIG,'-n',NAMESPACE,'exec','-i',name,'--',*command]
        p=await asyncio.create_subprocess_exec(*argv,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        async def bounded(stream):
            out=bytearray()
            while chunk:=await stream.read(65536):
                out.extend(chunk)
                if len(out)>max_bytes: raise RuntimeError('Sandbox output limit exceeded')
            return bytes(out)
        try:
            p.stdin.write(json.dumps(data).encode() if data is not None else b''); await p.stdin.drain(); p.stdin.close()
            stdout,stderr=await asyncio.wait_for(asyncio.gather(bounded(p.stdout),bounded(p.stderr)),timeout)
            await p.wait()
            if p.returncode: raise RuntimeError('Sandbox execution failed: '+stderr.decode(errors='replace')[:500])
            return stdout.decode()
        finally:
            if p.returncode is None: p.kill(); await p.wait()
    async def quick(self,code,run,store,input_files=None):
        queued=time.perf_counter();self.queued+=1;self.policy.touch();self.refill.set()
        run['status']='queued';store.save_run(run);entered=False
        try:
            async with self.slots:
                self.queued-=1;self.executing+=1;entered=True
                run['timings']={'queue_seconds':round(time.perf_counter()-queued,4)}
                try: return await self._quick(code,run,store,input_files)
                finally:
                    self.executing-=1;self.policy.touch();self.refill.set()
                    run['timings']['total_seconds']=round(time.perf_counter()-queued,4);store.save_run(run)
        finally:
            if not entered: self.queued-=1;self.refill.set()
    async def _quick(self,code,run,store,input_files):
        files=inputs(store,run['thread_id'],input_files or []);started=time.perf_counter()
        name=await self.acquire();run['timings']['acquire_seconds']=round(time.perf_counter()-started,4)
        run.update(pod=name,status='running');store.save_run(run);started=time.perf_counter()
        try:
            result=json.loads(await self.execute(name,['python','/opt/lab/quick.py'],{'code':code,'files':files,'checkpoint':checkpoints.load(run['thread_id'])}))
            checkpoint=result.pop('checkpoint',None)
            if checkpoint is not None:
                run['checkpoint']=checkpoints.save(run['thread_id'],run['id'],checkpoint)
                result['checkpoint']=run['checkpoint']
            # Always retain the submitted source in the ordinary conversation catalog.
            import base64
            result.setdefault('artifacts',[]).insert(0,{'name':'quick-source.py','data':base64.b64encode(code.encode()).decode()})
            return result
        finally:
            run['timings']['execute_seconds']=round(time.perf_counter()-started,4);started=time.perf_counter()
            try: await self.call('delete_namespaced_pod',name,NAMESPACE)
            finally:
                self.cache.pop(name,None);self.leased.discard(name);self.pending_created.pop(name,None);self.refill.set()
                run['timings']['cleanup_seconds']=round(time.perf_counter()-started,4)
compute=Compute()
