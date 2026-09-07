import asyncio
from types import SimpleNamespace
import httpx
import pytest


@pytest.mark.asyncio
async def test_many_status_requests_share_health_checks_and_recover_after_expiry():
    from backend.health import HealthCache
    calls=[]
    async def pool(): calls.append('pool'); await asyncio.sleep(.01); return [1,2]
    async def ready(): calls.append('coder'); return True
    cache=HealthCache()
    compute=SimpleNamespace(pool=pool,ready=True); coder=SimpleNamespace(ready=ready)
    values=await asyncio.gather(*(cache.get(compute,coder) for _ in range(20)))
    assert calls==['pool','coder']
    assert all(v=={'kubernetes':True,'warm_pods':2,'coder':True} for v in values)
    values[0]['coder']=False
    assert (await cache.get(compute,coder))['coder'] is True
    async def failed(): raise RuntimeError('temporarily unavailable')
    compute.pool=failed;cache.expires=0
    assert (await cache.get(compute,coder))['kubernetes'] is False
    compute.pool=pool;cache.expires=0
    assert (await cache.get(compute,coder))['kubernetes'] is True


@pytest.mark.asyncio
async def test_refill_happens_while_claimed_pod_is_executing(monkeypatch):
    from backend.compute import Compute
    pool=Compute(); pool.pool_size=1
    pods={'initial':'warm'}; executing=asyncio.Event(); finish=asyncio.Event()
    class Store:
        def save_run(self,run): pass
    async def call(method,*args,**kwargs):
        if method=='list_namespaced_pod':
            return SimpleNamespace(items=[SimpleNamespace(metadata=SimpleNamespace(name=n,labels={'lab/state':s},resource_version='1',deletion_timestamp=None),status=SimpleNamespace(phase='Running')) for n,s in pods.items()])
        if method=='patch_namespaced_pod': pods[args[0]]='leased'
        if method=='create_namespaced_pod': pods[args[1]['metadata']['name']]='warm'
        if method=='delete_namespaced_pod': pods.pop(args[0])
    async def execute(*args,**kwargs):
        executing.set(); await finish.wait(); return '{"stdout":"42"}'
    monkeypatch.setattr(pool,'call',call); monkeypatch.setattr(pool,'execute',execute)
    async def observe():
        while not pool.stop_watch.is_set():
            await pool.snapshot();await asyncio.sleep(.01)
    monkeypatch.setattr(pool,'observe',observe)
    pool.policy.warm()
    monkeypatch.setattr('backend.compute.inputs',lambda *args: [])
    maintainer=asyncio.create_task(pool.maintain())
    run={'id':'r','thread_id':'t'}
    work=asyncio.create_task(pool.quick('print(42)',run,Store()))
    try:
        await asyncio.wait_for(executing.wait(),1)
        async with asyncio.timeout(1):
            while not any(n!='initial' and s=='warm' for n,s in pods.items()): await asyncio.sleep(.001)
        assert not work.done() and pods['initial']=='leased'
        finish.set(); await work
        assert 'initial' not in pods
        assert all(run['timings'][s]>=0 for s in ['queue_seconds','acquire_seconds','execute_seconds','cleanup_seconds','total_seconds'])
    finally:
        finish.set(); maintainer.cancel()
        await asyncio.gather(work,maintainer,return_exceptions=True)


@pytest.mark.asyncio
async def test_embedded_workspace_is_authenticated_owned_and_separate_from_preview(monkeypatch):
    import backend.main as module
    ws={'id':'owned','name':'dev','status':'running','ide_url':'http://127.0.0.1:7080/@developer/dev/apps/vscode/'}
    async def listing(): return [ws]
    seen={}
    async def expose(workspace,settings,**kwargs):
        seen.update(kwargs); seen['id']=workspace['id']
        return 'http://127.0.0.1:5555/'
    monkeypatch.setattr(module.developer,'list',listing)
    async def prepare(workspace): pass
    monkeypatch.setattr(module.developer,'prepare',prepare)
    monkeypatch.setattr(module.developer,'token','test-token')
    monkeypatch.setattr(module.previews,'app',expose)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://127.0.0.1:8787') as c:
        assert (await c.get('/api/developer/workspaces/owned/open?resolve=1')).status_code==401
        await c.post('/api/bootstrap')
        assert (await c.get('/api/developer/workspaces/other/open?resolve=1')).status_code==404
        r=await c.get('/api/developer/workspaces/owned/open?resolve=1')
        assert r.json()=={'url':ws['ide_url']}
        assert 'httponly' in r.headers['set-cookie'].lower() and 'test-token' not in r.text
        r=await c.get('/api/developer/workspaces/owned/preview?resolve=1')
        assert r.json()['url']=='http://127.0.0.1:5555/'
        assert seen=={'id':'owned','coder_url':'http://127.0.0.1:7080'}
        ws['status']='stopped'
        assert (await c.get('/api/developer/workspaces/owned/open?resolve=1')).status_code==409
