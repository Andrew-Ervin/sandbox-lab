import base64,hashlib,importlib.util,json,time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from chatkit.store import NotFoundError
from chatkit.types import ThreadMetadata
from backend.store import SQLiteStore
from backend.workspace_links import WorkspaceLinks,checked_files

def file(path='main.py',raw=b'print(42)'):
    return {'path':path,'data':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()}

@pytest.fixture
def importer():
    spec=importlib.util.spec_from_file_location('project_importer',Path(__file__).parents[1]/'sandbox/import_project.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_import_creates_separate_snapshot_and_preserves_live_files(tmp_path,importer):
    (tmp_path/'main.py').write_text('live edits')
    key='transfer_'+'a'*32
    result=importer.publish({'id':key,'files':[file(),file('src/app.go',b'package main')]},str(tmp_path))
    assert (tmp_path/'main.py').read_text()=='live edits'
    assert (tmp_path/result['path']/'main.py').read_text()=='print(42)'
    assert (tmp_path/result['path']/'src/app.go').read_text()=='package main'
    with pytest.raises(ValueError,match='already exists'):importer.publish({'id':key,'files':[file()]},str(tmp_path))

@pytest.mark.parametrize('path',['../escape','/etc/passwd','.env','src/private.key','.config/token','node_modules/token','.lab/imports/previous/code.py'])
def test_import_rejects_unsafe_or_recursive_paths_before_writing(tmp_path,importer,path):
    with pytest.raises(ValueError):importer.publish({'id':'transfer_'+'a'*32,'files':[file(path)]},str(tmp_path))
    assert not (tmp_path/'.lab').exists()

def test_import_rejects_symlinked_root_and_failed_checksum(tmp_path,importer):
    root=tmp_path/'project';root.mkdir();outside=tmp_path/'outside';outside.mkdir();(root/'.lab').symlink_to(outside)
    with pytest.raises(OSError):importer.publish({'id':'transfer_'+'a'*32,'files':[file()]},str(root))
    assert list(outside.iterdir())==[]
    invalid=file();invalid['sha256']='bad'
    with pytest.raises(ValueError,match='checksum'):importer.publish({'id':'transfer_'+'b'*32,'files':[invalid]},str(tmp_path))

def test_import_storage_limit_never_removes_previous_snapshots(tmp_path,importer):
    for c in 'abc':importer.publish({'id':'transfer_'+c*32,'files':[file()]},str(tmp_path))
    with pytest.raises(ValueError,match='three snapshots'):importer.publish({'id':'transfer_'+'d'*32,'files':[file()]},str(tmp_path))
    assert len(list((tmp_path/'.lab/imports').iterdir()))==3

def test_linking_creates_only_project_metadata_and_never_reuses_dev_id_for_execution(tmp_path):
    store=SQLiteStore(tmp_path/'db');p=store.link_developer('dev','alice','Developer')
    assert p['workspace_id'] is None and p['developer_workspace_id']=='dev'
    assert store.projects('alice')[0]['threads']==[]
    assert store.link_developer('dev','alice','Developer')['id']==p['id']
    with pytest.raises(NotFoundError):store.link_developer('dev','bob','Developer')

@pytest.mark.asyncio
async def test_linked_project_chat_keeps_a_distinct_headless_workspace(tmp_path):
    store=SQLiteStore(tmp_path/'db');p=store.link_developer('dev','alice','Developer')
    thread=ThreadMetadata(id='t',created_at=datetime.now(timezone.utc));await store.save_thread(thread,{'owner':'alice'});store.attach_project(thread,'alice',p['id'])
    assert 'coder_workspace_id' not in thread.metadata
    thread.metadata['coder_workspace_id']='headless';await store.save_thread(thread,{'owner':'alice'})
    assert store.get_project(p['id'],'alice')['workspace_id']=='headless'
    assert store.get_project(p['id'],'alice')['developer_workspace_id']=='dev'

@pytest.mark.asyncio
async def test_link_move_changes_association_without_merging_files_or_chat_membership(tmp_path):
    store=SQLiteStore(tmp_path/'db');p=store.link_developer('dev','alice','Developer')
    t=ThreadMetadata(id='t',created_at=datetime.now(timezone.utc));await store.save_thread(t,{'owner':'alice'});other=store.ensure_project(t,'alice')
    store.link_developer('dev','alice','Developer',other['id'])
    assert store.get_project(p['id'],'alice')['developer_workspace_id'] is None
    assert store.project_for_thread('t','alice')['id']==other['id']
    store.update_project(other['id'],'alice',archived=True)
    with pytest.raises(ValueError):store.link_developer('different','alice','Other',other['id'])

@pytest.fixture
def transfer_setup(tmp_path):
    store=SQLiteStore(tmp_path/'db');p=store.link_developer('dev','alice','Developer')
    with store.db:store.db.execute('UPDATE projects SET workspace_id=? WHERE id=?',('headless',p['id']))
    coder=SimpleNamespace(project_locks={},active=set(),provisioning=set())
    dev=SimpleNamespace(list=AsyncMock(return_value=[{'id':'dev','name':'dev','status':'running'}]),prepare=AsyncMock(),touched={})
    links=WorkspaceLinks(store,coder,dev)
    links.browser.workspace=AsyncMock(return_value={'id':'headless','name':'ai'})
    links.browser.read=AsyncMock(side_effect=[{'files':[file()]},{'files':[file(raw=b'original')]}])
    links.browser.invoke=AsyncMock(return_value={'path':'.lab/imports/test','file_count':1,'bytes':9})
    return store,p,links

@pytest.mark.asyncio
async def test_sync_review_does_not_write_and_approval_is_owner_bound(transfer_setup):
    store,p,links=transfer_setup
    plan=await links.plan(p['id'],'alice','to_chat')
    assert plan['files'][0]['change']=='different'
    links.browser.invoke.assert_not_awaited()
    with pytest.raises(HTTPException) as e:await links.apply(p['id'],'bob',plan['id'])
    assert e.value.status_code==404
    result=await links.apply(p['id'],'alice',plan['id'])
    assert result['direction']=='to_chat'
    ws,script,payload,dev=links.browser.invoke.call_args.args
    assert ws['id']=='headless' and dev is None and payload['files'][0]['sha256']==file()['sha256']
    assert plan['id'] not in links.plans
    assert store.get_project(p['id'],'alice')['workspace_sync']['file_count']==1

@pytest.mark.asyncio
async def test_sync_rejects_expiry_changed_links_and_active_execution(transfer_setup):
    store,p,links=transfer_setup;plan=await links.plan(p['id'],'alice','to_developer')
    links.coder.active.add('headless')
    with pytest.raises(HTTPException) as e:await links.apply(p['id'],'alice',plan['id'])
    assert e.value.status_code==409;links.coder.active.clear()
    with store.db:store.db.execute('UPDATE projects SET developer_workspace_id=? WHERE id=?',('changed',p['id']))
    with pytest.raises(HTTPException) as e:await links.apply(p['id'],'alice',plan['id'])
    assert e.value.status_code==409
    links.plans[plan['id']]['expires']=time.monotonic()-1
    with pytest.raises(HTTPException) as e:await links.apply(p['id'],'alice',plan['id'])
    assert e.value.status_code==404;links.browser.invoke.assert_not_awaited()

@pytest.mark.asyncio
async def test_sync_cannot_allocate_a_chat_workspace(transfer_setup):
    store,p,links=transfer_setup
    with store.db:store.db.execute('UPDATE projects SET workspace_id=NULL WHERE id=?',(p['id'],))
    with pytest.raises(HTTPException) as e:await links.plan(p['id'],'alice','to_chat')
    assert e.value.status_code==409;links.browser.workspace.assert_not_awaited()

def test_source_validation_checks_duplicates_and_credentials():
    with pytest.raises(ValueError):checked_files({'files':[file(),file()]})
    with pytest.raises(ValueError):checked_files({'files':[file('.config/token')]})

@pytest.mark.asyncio
async def test_open_project_developer_creates_once_without_allocating_headless(transfer_setup):
    store,p,links=transfer_setup
    with store.db:store.db.execute('UPDATE projects SET developer_workspace_id=NULL,developer_name=NULL,workspace_id=NULL WHERE id=?',(p['id'],))
    links.developer.start=AsyncMock(return_value={'id':'dev','name':'project-dev','status':'running'})
    first=await links.open_developer(p['id'],'alice')
    second=await links.open_developer(p['id'],'alice')
    assert first['id']==second['id']=='dev'
    links.developer.start.assert_awaited_once()
    assert store.get_project(p['id'],'alice')['workspace_id'] is None
    links.browser.workspace.assert_not_awaited()
    with pytest.raises(HTTPException) as error:await links.open_developer(p['id'],'bob')
    assert error.value.status_code==404

@pytest.mark.asyncio
async def test_open_project_developer_rejects_archive_and_busy_project(transfer_setup):
    import asyncio
    store,p,links=transfer_setup
    lock=links.coder.project_locks.setdefault(p['id'],asyncio.Lock())
    async with lock:
        with pytest.raises(HTTPException) as error:await links.open_developer(p['id'],'alice')
        assert error.value.status_code==409
    store.update_project(p['id'],'alice',archived=True)
    with pytest.raises(HTTPException) as error:await links.open_developer(p['id'],'alice')
    assert error.value.status_code==409


@pytest.mark.asyncio
async def test_open_project_copies_source_and_returns_exact_editor_folder(transfer_setup):
    store,p,links=transfer_setup
    links.browser.read=AsyncMock(return_value={'files':[file()]})
    async def publish(ws,script,payload,developer):
        assert ws['id']=='dev' and developer is links.developer
        assert payload['reuse'] is True and payload['files'][0]['sha256']==hashlib.sha256(base64.b64decode(payload['files'][0]['data'])).hexdigest()
        return {'path':'.lab/imports/'+payload['id'],'file_count':1,'bytes':9}
    links.browser.invoke=AsyncMock(side_effect=publish)
    first=await links.open_developer(p['id'],'alice')
    second=await links.open_developer(p['id'],'alice')
    assert first['source_path']==second['source_path']
    assert first['source_path'].startswith('.lab/imports/transfer_')
    assert links.browser.read.await_count==2  # No destination export or separate review.
    assert store.get_project(p['id'],'alice')['workspace_id']=='headless'
    assert store.get_project(p['id'],'alice')['workspace_sync']['direction']=='to_developer'
    links.browser.read.return_value={'files':[file(raw=b'updated source')]}
    third=await links.open_developer(p['id'],'alice')
    assert third['source_path']!=first['source_path']


def test_reopening_identical_snapshot_preserves_developer_edits_at_capacity(tmp_path,importer):
    key='transfer_'+'a'*32
    result=importer.publish({'id':key,'files':[file()],'reuse':True},str(tmp_path))
    edited=tmp_path/result['path']/'main.py';edited.write_text('developer edits')
    for c in 'bc':importer.publish({'id':'transfer_'+c*32,'files':[file()]},str(tmp_path))
    again=importer.publish({'id':key,'files':[file()],'reuse':True},str(tmp_path))
    assert again['reused'] is True and edited.read_text()=='developer edits'
    assert len(list((tmp_path/'.lab/imports').iterdir()))==3


def test_reuse_rejects_symlinked_destination(tmp_path,importer):
    key='transfer_'+'a'*32
    inbox=tmp_path/'.lab/imports';inbox.mkdir(parents=True)
    (inbox/key).symlink_to(tmp_path)
    with pytest.raises(OSError):importer.publish({'id':key,'files':[file()],'reuse':True},str(tmp_path))


def test_editor_folder_is_bounded_to_copied_source():
    from backend.apps import developer_source_url
    from urllib.parse import urlsplit,parse_qs
    url=developer_source_url('http://127.0.0.1:7080/apps/vscode/','.lab/imports/transfer_'+'a'*32)
    assert parse_qs(urlsplit(url).query)['folder']==['/home/sandbox/project/.lab/imports/transfer_'+'a'*32]
    for invalid in ('../../.config','/etc','https://example.invalid',{'folder':'anything'}):
        with pytest.raises(ValueError):developer_source_url('http://127.0.0.1:7080/',invalid)


@pytest.mark.asyncio
async def test_return_copy_reads_opened_developer_folder_and_retains_it(transfer_setup):
    store,p,links=transfer_setup;path='.lab/imports/transfer_'+'a'*32
    with store.db:store.db.execute('UPDATE projects SET workspace_sync=? WHERE id=?',(json.dumps({'developer_source_path':path}),p['id']))
    plan=await links.plan(p['id'],'alice','to_chat')
    assert links.browser.read.call_args_list[0].kwargs['path']==path
    await links.apply(p['id'],'alice',plan['id'])
    assert store.get_project(p['id'],'alice')['workspace_sync']['developer_source_path']==path
