from datetime import datetime,timezone
import httpx
import pytest
from chatkit.types import ThreadMetadata
from backend.store import SQLiteStore

@pytest.mark.asyncio
async def test_gallery_retains_old_apps_but_not_hidden_or_other_owners(tmp_path):
    store=SQLiteStore(tmp_path/'db')
    for owner in ['alice','bob']:
        await store.save_thread(ThreadMetadata(id=owner,title=owner,created_at=datetime.now(timezone.utc)),{'owner':owner})
        store.save_run({'id':owner,'thread_id':owner,'mode':'app','preview_url':'/preview','workspace_id':owner})
    for i in range(65):store.save_run({'id':str(i),'thread_id':'alice','status':'completed'})
    assert len(store.runs('alice'))==60
    store.save_run({'id':'hidden','thread_id':'alice','preview_url':'/hidden','gallery_hidden':True})
    assert [a['id'] for a in store.apps('alice')]==['alice']
    store.save_run({'id':'newer','thread_id':'alice','preview_url':'/new','workspace_id':'alice'})
    assert [a['id'] for a in store.apps('alice')]==['newer']
    assert store.apps('alice')[0]['title']=='alice'

@pytest.mark.asyncio
async def test_static_app_is_owner_scoped_and_never_starts_workspace(tmp_path,monkeypatch):
    import backend.main as module
    store=SQLiteStore(tmp_path/'db');monkeypatch.setattr(module,'store',store);monkeypatch.setattr(module,'STATE',tmp_path)
    await store.save_thread(ThreadMetadata(id='a',created_at=datetime.now(timezone.utc)),{'owner':'local-owner'})
    await store.save_thread(ThreadMetadata(id='b',created_at=datetime.now(timezone.utc)),{'owner':'someone-else'})
    folder=tmp_path/'artifacts'/'guide';folder.mkdir(parents=True);(folder/'guide.html').write_text('<h1>Guide</h1>')
    run={'id':'guide','thread_id':'a','mode':'app','preview_artifact':'guide.html','artifacts':[{'name':'guide.html'}]};store.save_run(run)
    store.save_run({**run,'id':'foreign','thread_id':'b'})
    opened=[]
    async def artifact(path):opened.append(path);return 'http://127.0.0.1:45678/'
    async def no_workspace(*args,**kwargs):raise AssertionError('Static app must not use a workspace')
    monkeypatch.setattr(module.previews,'artifact',artifact);monkeypatch.setattr(module.coder,'api',no_workspace)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://127.0.0.1:8787') as client:
        assert (await client.get('/api/app-preview/guide?resolve=1')).status_code==401
        await client.post('/api/bootstrap')
        assert (await client.get('/api/app-preview/foreign?resolve=1')).status_code==404
        response=await client.get('/api/app-preview/guide?resolve=1')
        assert response.json()=={'url':'http://127.0.0.1:45678/'}
        assert opened==[folder/'guide.html']
        (folder/'guide.html').unlink();(folder/'guide.html').symlink_to(tmp_path/'db')
        assert (await client.get('/api/app-preview/guide?resolve=1')).status_code==404
        store.save_run({**run,'preview_artifact':'../db','artifacts':[{'name':'../db'}]})
        assert (await client.get('/api/app-preview/guide?resolve=1')).status_code==404
