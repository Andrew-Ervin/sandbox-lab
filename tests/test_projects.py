import asyncio,base64,importlib.util,json,sqlite3
from pathlib import Path
from datetime import datetime,timezone
import pytest
from chatkit.types import ThreadMetadata
from chatkit.store import NotFoundError
from backend.store import SQLiteStore
from backend.projects import write_mock_sync

async def chat(store,id,owner='alice',wid=None):
    t=ThreadMetadata(id=id,title='Project '+id,created_at=datetime.now(timezone.utc),metadata={'coder_workspace_id':wid} if wid else {})
    await store.save_thread(t,{'owner':owner});return t

@pytest.mark.asyncio
async def test_migration_groups_shared_workspaces_without_touching_history(tmp_path):
    s=SQLiteStore(tmp_path/'db');a=await chat(s,'a',wid='ws-1');b=await chat(s,'b',wid='ws-1');c=await chat(s,'c',wid='ws-2');quick=await chat(s,'q')
    before=s.db.execute('SELECT id,updated FROM threads ORDER BY id').fetchall()
    s.remember_file('a','keep.txt','run_a',12)
    assert s.migrate_projects()==3
    assert len(s.projects('alice'))==2
    assert s.project_for_thread('a','alice')['id']==s.project_for_thread('b','alice')['id']
    assert s.project_for_thread('q','alice') is None
    assert s.files('a')[0]['name']=='keep.txt'
    assert s.migrate_projects()==0
    assert before==s.db.execute('SELECT id,updated FROM threads ORDER BY id').fetchall()

@pytest.mark.asyncio
async def test_project_binding_survives_stale_thread_saves_and_is_shared(tmp_path):
    s=SQLiteStore(tmp_path/'db');a=await chat(s,'a');project=s.ensure_project(a,'alice');b=await chat(s,'b');s.attach_project(b,'alice',project['id'])
    stale=await s.load_thread('b',{'owner':'alice'})
    a.metadata['coder_workspace_id']='shared-ws';await s.save_thread(a,{'owner':'alice'})
    await s.save_thread(stale,{'owner':'alice'})
    assert (await s.load_thread('b',{'owner':'alice'})).metadata['coder_workspace_id']=='shared-ws'
    assert s.ensure_project(stale,'alice')['workspace_id']=='shared-ws'
    assert len(s.projects('alice'))==1

@pytest.mark.asyncio
async def test_project_ownership_and_merge_boundaries(tmp_path):
    s=SQLiteStore(tmp_path/'db');a=await chat(s,'a','alice',wid='ws1');b=await chat(s,'b','bob');other=await chat(s,'c','alice',wid='ws2')
    p=s.ensure_project(a,'alice')
    with pytest.raises(NotFoundError):s.get_project(p['id'],'bob')
    with pytest.raises(NotFoundError):s.attach_project(b,'bob',p['id'])
    with pytest.raises(ValueError):s.attach_project(other,'alice',p['id'])
    await s.delete_thread('a',{'owner':'alice'})
    assert s.get_project(p['id'],'alice')['workspace_id']=='ws1'

@pytest.mark.asyncio
async def test_migration_recovers_workspace_from_existing_run(tmp_path):
    s=SQLiteStore(tmp_path/'db');await chat(s,'a')
    s.save_run({'id':'r','thread_id':'a','mode':'app','workspace_id':'old-ws'})
    assert s.migrate_projects()==1
    assert s.project_for_thread('a','alice')['workspace_id']=='old-ws'

@pytest.fixture
def reader():
    spec=importlib.util.spec_from_file_location('project_reader',Path(__file__).parents[1]/'sandbox/project_files.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_browser_preserves_nested_source_and_rejects_symlinks_credentials(tmp_path,reader):
    root=tmp_path/'project';root.mkdir();(root/'src').mkdir();(root/'src/app.py').write_text('print(42)')
    (root/'.env').write_text('private');(root/'node_modules').mkdir();(root/'node_modules/data').write_text('dependency')
    (root/'escape').symlink_to(tmp_path/'outside');(tmp_path/'outside').write_text('outside')
    result=reader.execute({'action':'list'},str(root))
    assert [e['name'] for e in result['entries']]==['src']
    result=reader.execute({'action':'export'},str(root));assert [f['path'] for f in result['files']]==['src/app.py']
    assert base64.b64decode(reader.execute({'action':'read','path':'src/app.py'},str(root))['data'])==b'print(42)'
    for path in ['../outside','.env','escape','/etc/passwd']:
        with pytest.raises((OSError,ValueError)):reader.execute({'action':'read','path':path},str(root))
    (root/'src').rename(root/'old-src');(root/'src').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(OSError):reader.execute({'action':'read','path':'src/outside'},str(root))

def test_export_of_opened_developer_copy_is_relative_and_excludes_nested_imports(tmp_path,reader):
    folder=tmp_path/'.lab/imports/transfer_abc';folder.mkdir(parents=True)
    (folder/'main.py').write_text('developer edits')
    (tmp_path/'unrelated.py').write_text('unrelated root file')
    nested=folder/'.lab/imports/old';nested.mkdir(parents=True);(nested/'other.py').write_text('old import')
    result=reader.execute({'action':'export','path':'.lab/imports/transfer_abc'},str(tmp_path))
    assert [f['path'] for f in result['files']]==['main.py']
    assert base64.b64decode(result['files'][0]['data'])==b'developer edits'

def test_mock_sync_is_local_bounded_and_retains_previous_on_invalid_export(tmp_path):
    pid='prj_'+'a'*32
    data=lambda path,text:{'path':path,'data':base64.b64encode(text.encode()).decode()}
    first=write_mock_sync(pid,{'files':[data('src/main.py','old')],'excluded':2},tmp_path)
    assert first['mock'] and first['file_count']==1
    with pytest.raises(ValueError):write_mock_sync(pid,{'files':[data('../../escape','evil')]},tmp_path)
    assert (tmp_path/pid/'files/src/main.py').read_text()=='old'
    write_mock_sync(pid,{'files':[data('src/new.py','new')]},tmp_path)
    assert not (tmp_path/pid/'files/src/main.py').exists()
    assert (tmp_path/pid/'files/src/new.py').read_text()=='new'
    assert not (tmp_path/pid/'previous').exists()
    with pytest.raises(ValueError):write_mock_sync(pid,{'files':[data('.env','secret')]},tmp_path)

def test_large_directory_browser_truncates_and_export_fails_before_unbounded_scanning(tmp_path,reader,monkeypatch):
    from types import SimpleNamespace
    from contextlib import contextmanager
    monkeypatch.setattr(reader,'MAX_ENTRIES',20)
    visited=[]
    @contextmanager
    def scan(fd):
        def entries():
            for i in range(1_000_000):
                visited.append(i)
                yield SimpleNamespace(name=f'.hidden-{i}')
        yield entries()
    monkeypatch.setattr(reader.os,'scandir',scan)
    result=reader.execute({'action':'list'},str(tmp_path))
    assert result['truncated'] and result['entries']==[] and result['excluded']==20
    assert len(visited)==21
    visited.clear()
    with pytest.raises(ValueError,match='too many entries'):reader.execute({'action':'export'},str(tmp_path))
    assert len(visited)==21

def test_browser_file_limit_is_explicit_and_export_budget_is_shared_by_subfolders(tmp_path,reader,monkeypatch):
    monkeypatch.setattr(reader,'MAX_FILES',2)
    for name in ['c.txt','b.txt','a.txt']:(tmp_path/name).write_text(name)
    result=reader.execute({'action':'list'},str(tmp_path))
    assert result['truncated'] and len(result['entries'])==2
    assert [e['name'] for e in result['entries']]==sorted(e['name'] for e in result['entries'])
    monkeypatch.setattr(reader,'MAX_FILES',20)
    assert not reader.execute({'action':'list'},str(tmp_path))['truncated']
    (tmp_path/'src').mkdir();(tmp_path/'src/nested.txt').write_text('nested')
    monkeypatch.setattr(reader,'MAX_ENTRIES',4)
    with pytest.raises(ValueError,match='too many entries'):reader.execute({'action':'export'},str(tmp_path))
    monkeypatch.setattr(reader,'MAX_ENTRIES',5)
    assert len(reader.execute({'action':'export'},str(tmp_path))['files'])==4

@pytest.mark.asyncio
async def test_new_thread_reuses_project_workspace_without_creating_another(tmp_path,monkeypatch):
    from backend.coder import CoderAgents
    s=SQLiteStore(tmp_path/'db');a=await chat(s,'a',wid='shared');p=s.ensure_project(a,'alice');b=await chat(s,'b');s.attach_project(b,'alice',p['id'])
    coder=CoderAgents();monkeypatch.setattr(coder,'settings',lambda:{'template_id':'template'})
    calls=[]
    async def api(method,path,**kw):calls.append(method);return {'id':'shared','template_id':'template','latest_build':{'status':'running'}}
    monkeypatch.setattr(coder,'api',api)
    assert await coder.allocate(b,s,{'owner':'alice'})=='shared'
    assert calls==['GET']

@pytest.mark.asyncio
async def test_project_routes_enforce_owner_and_create_shared_chat(tmp_path):
    import httpx
    from fastapi import FastAPI,Request
    from types import SimpleNamespace
    from backend.projects import install_projects
    s=SQLiteStore(tmp_path/'db');a=await chat(s,'a',wid='shared');p=s.ensure_project(a,'alice')
    app=FastAPI()
    @app.middleware('http')
    async def identity(request:Request,next):request.state.owner=request.headers.get('test-owner','alice');return await next(request)
    async def live():return {'pods':[],'unavailable_namespaces':[]}
    coder=SimpleNamespace(project_locks={},active=set(),provisioning=set())
    install_projects(app,s,coder,SimpleNamespace(get=live))
    from backend.workspace_links import install_workspace_links
    install_workspace_links(app,s,coder,SimpleNamespace())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        for method,path in [('GET','files'),('GET','file?path=main.py'),('POST','open'),('POST','threads'),('POST','sync-onedrive')]:
            assert (await client.request(method,f'/api/projects/{p["id"]}/{path}',headers={'test-owner':'bob'})).status_code==404
        result=await client.post(f'/api/projects/{p["id"]}/threads');assert result.status_code==200
        child=await s.load_thread(result.json()['id'],{'owner':'alice'})
        assert child.metadata['coder_workspace_id']=='shared'
        assert child.metadata['project_id']==p['id']
