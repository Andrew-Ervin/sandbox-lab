import base64,hashlib,json
from types import SimpleNamespace
import pytest
from backend.source_sync import SourceSync,reconcile
from backend.store import SQLiteStore
from backend.workspace_links import WorkspaceLinks
from sandbox import project_files,sync_project

def digest(text):return hashlib.sha256(text.encode()).hexdigest()

def test_three_way_changes_deletions_and_conflicts():
    changes,conflicts,agreed=reconcile({'same':'a','left':'a','right':'a','delete':'a','both':'a'},
        {'same':'a','left':'b','right':'a','both':'b'},
        {'same':'a','left':'a','right':'c','delete':'a','both':'c'})
    assert changes=={'chat':{'right':'c'},'developer':{'delete':None,'left':'b'}}
    assert conflicts==['both'] and agreed=={'same':'a'}
    changes,conflicts,_=reconcile({'big':'a'},{},{'big':'a'},['big'])
    assert conflicts==['big'] and not any(changes.values())

@pytest.fixture
def setup(tmp_path):
    folders={name:tmp_path/name for name in ('chat','developer')}
    for folder in folders.values():folder.mkdir()
    store=SQLiteStore(tmp_path/'db');p=store.link_developer('developer','alice','Developer')
    with store.db:store.db.execute('UPDATE projects SET workspace_id=? WHERE id=?',('chat',p['id']))
    async def read(ws,action,path='',developer=None):return project_files.execute({'action':action,'path':path},str(folders[ws['id']]))
    async def invoke(ws,script,payload,developer=None):return sync_project.apply(payload,str(folders[ws['id']]))
    links=SimpleNamespace(store=store,developer=object(),browser=SimpleNamespace(read=read,invoke=invoke),paths=WorkspaceLinks.paths)
    engine=SourceSync(links)
    async def run(**kw):return await engine.run(store.get_project(p['id'],'alice'),'alice',{'id':'chat'},{'id':'developer'},**kw)
    return folders,store,p,run

@pytest.mark.asyncio
async def test_bidirectional_sync_preserves_conflicts_and_tracks_deletions(setup):
    folders,store,p,run=setup;a,b=folders.values()
    (b/'app.py').write_text('first');(b/'.env').write_text('private');(b/'node_modules').mkdir();(b/'node_modules/private').write_text('private')
    result=await run();assert result['state']=='synced' and (a/'app.py').read_text()=='first'
    assert not (a/'.env').exists() and not (a/'node_modules').exists()
    (a/'app.py').write_text('chat edit');await run();assert (b/'app.py').read_text()=='chat edit'
    (b/'new.txt').write_text('new');await run();assert (a/'new.txt').read_text()=='new'
    (a/'new.txt').unlink();await run();assert not (b/'new.txt').exists()
    (a/'app.py').write_text('chat conflict');(b/'app.py').write_text('dev conflict')
    result=await run();assert result['conflicts']==['app.py']
    assert (a/'app.py').read_text()=='chat conflict' and (b/'app.py').read_text()=='dev conflict'
    # Restarting the sync service reads the durable common baseline.
    result=await run(resolution=('app.py','developer'))
    assert result['state']=='synced' and (a/'app.py').read_text()=='dev conflict'
    assert (await run())['copied']==0
    assert 'base' not in store.get_project(p['id'],'alice')['workspace_sync']

def test_apply_compares_current_hash_and_refuses_symlinks(tmp_path):
    (tmp_path/'file.txt').write_text('newer local edit')
    patch={'path':'file.txt','before':digest('old'),'data':base64.b64encode(b'remote').decode()}
    assert sync_project.apply({'changes':[patch]},str(tmp_path))['conflicts']==['file.txt']
    assert (tmp_path/'file.txt').read_text()=='newer local edit'
    outside=tmp_path/'outside';outside.mkdir();(tmp_path/'link').symlink_to(outside)
    patch.update(path='link/escape',before=None)
    assert sync_project.apply({'changes':[patch]},str(tmp_path))['conflicts']==['link/escape']
    assert list(outside.iterdir())==[]
    for path in ('../escape','.env','.lab/imports/again/x','node_modules/x'):
        with pytest.raises(ValueError):sync_project.apply({'changes':[{**patch,'path':path}]},str(tmp_path))

@pytest.mark.asyncio
async def test_oversized_source_is_not_mistaken_for_a_deletion(setup,monkeypatch):
    folders,store,p,run=setup;a,b=folders.values()
    (b/'file.txt').write_text('original');await run()
    monkeypatch.setattr(project_files,'MAX_FILE',10)
    (b/'file.txt').write_text('now too large to synchronize')
    result=await run()
    assert result['conflicts']==['file.txt'] and (a/'file.txt').read_text()=='original'

def test_manifest_has_hashes_and_no_contents(tmp_path):
    (tmp_path/'file.txt').write_text('content')
    result=project_files.execute({'action':'manifest'},str(tmp_path))
    assert result['files'][0]['sha256']==digest('content') and 'data' not in result['files'][0]
