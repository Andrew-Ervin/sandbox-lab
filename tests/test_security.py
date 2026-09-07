import asyncio,importlib.util,json,os
from datetime import datetime,timezone
from pathlib import Path
import pytest
from chatkit.types import ThreadMetadata, AssistantMessageItem,AssistantMessageContent
from chatkit.store import NotFoundError
from backend.store import SQLiteStore
from backend.compute import pod_manifest

def test_quick_pod_is_restricted_and_ephemeral():
    p=pod_manifest('test')['spec']; c=p['containers'][0]
    assert p['automountServiceAccountToken'] is False
    assert p['securityContext']['runAsNonRoot'] is True
    assert p['securityContext']['seccompProfile']['type']=='RuntimeDefault'
    assert not p.get('hostNetwork') and not p.get('hostPID') and not p.get('hostIPC')
    assert c['securityContext']['capabilities']['drop']==['ALL']
    assert c['securityContext']['readOnlyRootFilesystem'] is True
    assert c['securityContext']['allowPrivilegeEscalation'] is False
    assert all('emptyDir' in v for v in p['volumes'])
    assert not c.get('env') and not c.get('envFrom')
    assert c['resources']['limits']['memory']=='768Mi'

@pytest.mark.asyncio
async def test_store_ownership_and_pagination(tmp_path):
    s=SQLiteStore(tmp_path/'db'); a={'owner':'alice'}; b={'owner':'bob'}
    t=ThreadMetadata(id='thr_test',created_at=datetime.now(timezone.utc))
    await s.save_thread(t,a)
    for i in range(4):
        item=AssistantMessageItem(id=f'msg_{i}',thread_id=t.id,created_at=datetime.now(timezone.utc),content=[AssistantMessageContent(text=str(i))])
        await s.add_thread_item(t.id,item,a)
    page=await s.load_thread_items(t.id,None,2,'asc',a)
    assert [x.id for x in page.data]==['msg_0','msg_1'] and page.has_more
    rest=await s.load_thread_items(t.id,page.after,2,'asc',a)
    assert [x.id for x in rest.data]==['msg_2','msg_3'] and not rest.has_more
    for fn in [lambda:s.load_thread(t.id,b),lambda:s.load_thread_items(t.id,None,10,'asc',b),lambda:s.delete_thread(t.id,b),lambda:s.save_thread(t,b)]:
        with pytest.raises(NotFoundError): await fn()
    assert (await s.load_threads(10,None,'desc',b)).data==[]
    other=ThreadMetadata(id='thr_bob',created_at=datetime.now(timezone.utc))
    await s.save_thread(other,b)
    collision=AssistantMessageItem(id='msg_0',thread_id=other.id,created_at=datetime.now(timezone.utc),content=[AssistantMessageContent(text='overwrite')])
    with pytest.raises(NotFoundError): await s.save_item(other.id,collision,b)
    assert (await s.load_item(t.id,'msg_0',a)).content[0].text=='0'

def test_artifact_collector_refuses_links_fifos_and_large_files(tmp_path):
    spec=importlib.util.spec_from_file_location('collect',Path(__file__).parents[1]/'sandbox/collect.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    artifacts=tmp_path/'artifacts'; artifacts.mkdir(); module.ROOT=artifacts
    (artifacts/'ok.txt').write_text('42')
    secret=tmp_path/'secret'; secret.write_text('must not read')
    (artifacts/'link.txt').symlink_to(secret)
    os.mkfifo(artifacts/'pipe')
    (artifacts/'large.bin').write_bytes(b'0'*8_000_001)
    assert [x['name'] for x in module.collect()]==['ok.txt']

@pytest.mark.asyncio
async def test_local_http_auth_and_csrf():
    import httpx
    from backend.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8787') as c:
        assert (await c.get('/api/threads')).status_code==401
        assert (await c.post('/api/bootstrap',headers={'Origin':'https://evil.example'})).status_code==403
        assert (await c.post('/api/bootstrap',headers={'Host':'evil.example'})).status_code==403
        b=await c.post('/api/bootstrap'); assert b.status_code==200
        assert 'httponly' in b.headers['set-cookie'].lower()
        assert (await c.post('/api/chatkit',json={})).status_code==403
        assert (await c.get('/api/artifacts/run_unknown/passwd')).status_code==404
        assert (await c.post('/api/chatkit',json={},headers={'X-Lab-CSRF':b.json()['csrf'],'X-Lab-Mode':'invalid'})).status_code==400

@pytest.mark.asyncio
async def test_preview_strips_cookie_and_auth(monkeypatch):
    import httpx
    import backend.preview as module
    seen={}
    transport_client=httpx.AsyncClient
    class FakeClient:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*_): pass
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def stream(self,method,url,**kwargs):
            seen.update(kwargs)
            yield httpx.Response(200,content=b'<h1>preview</h1>',headers={'Content-Type':'text/html','Set-Cookie':'stolen=yes'})
    monkeypatch.setattr(module.httpx,'AsyncClient',FakeClient)
    module.targets[5555]={'kind':'app','upstream_port':5556,'expires':9999999999}
    async with transport_client(transport=httpx.ASGITransport(app=module.app),base_url='http://127.0.0.1:5555') as c:
        response=await c.get('/',headers={'Cookie':'lab_session=secret','Authorization':'Bearer secret'})
    assert response.status_code==200
    assert 'cookie' not in seen['headers'] and 'authorization' not in seen['headers']
    assert 'set-cookie' not in response.headers
    assert response.headers['Content-Security-Policy'].startswith('sandbox allow-scripts allow-forms;')
    assert 'allow-same-origin' not in response.headers['Content-Security-Policy']
