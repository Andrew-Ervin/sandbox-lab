import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.azure_storage import AzureStorage
from backend.azure_transport import AzureError


@pytest.fixture
def storage(tmp_path):
    transport=SimpleNamespace(call=AsyncMock())
    return AzureStorage(SimpleNamespace(root=tmp_path,config={'storage_account':'private'},transport=transport))


@pytest.mark.asyncio
async def test_conditional_save_invalidates_etag_on_conflict(storage):
    transport=storage.runtime.transport
    raw=json.dumps({'files':[]}).encode()
    transport.call.return_value={'data':base64.b64encode(raw).decode(),'etag':'v1'}
    await storage.load('workspaces','owner-project')
    transport.call.side_effect=AzureError('blob_put',412)
    with pytest.raises(AzureError):await storage.save('workspaces','owner-project',{'files':[{'path':'test.py'}]})
    assert storage.key('workspaces','owner-project') not in storage.index
    assert transport.call.call_args.kwargs['args']['etag']=='v1'
    assert storage.db.execute('SELECT SUM(bytes) FROM uploads').fetchone()[0]>0


@pytest.mark.asyncio
async def test_missing_blob_is_created_conditionally_and_unchanged_data_is_not_written(storage):
    transport=storage.runtime.transport
    transport.call.side_effect=[AzureError('blob_get',404),{'etag':'v1'}]
    await storage.save('chats','chat-one',{'files':[]})
    assert transport.call.call_args.kwargs['args']['etag'] is None
    count=transport.call.call_count
    await storage.save('chats','chat-one',{'files':[]})
    assert transport.call.call_count==count
    assert 'chat-one' not in storage.key('chats','chat-one')


@pytest.mark.asyncio
async def test_attempted_upload_allowance_stops_more_remote_writes(storage):
    storage.index[storage.key('chats','chat')]={'etag':'v1','sha256':'old','bytes':3}
    import time
    storage.db.execute('INSERT INTO uploads VALUES (?,?,?)',('prior',2_000_000_000,time.time()))
    with pytest.raises(RuntimeError,match='allowance'):await storage.save('chats','chat',{'files':[]})
    storage.runtime.transport.call.assert_not_called()


def test_root_bootstrap_rejects_symlink_parent_before_chown(tmp_path,monkeypatch):
    from sandbox.azure_bootstrap import ensure_directory
    target=tmp_path/'private';target.mkdir()
    link=tmp_path/'workspace';link.symlink_to(target,target_is_directory=True)
    chown=[];monkeypatch.setattr('os.fchown',lambda *args:chown.append(args))
    with pytest.raises(OSError):ensure_directory(str(link/'owned'),owner=1000)
    assert chown==[] and not (target/'owned').exists()


def test_root_bootstrap_uses_open_directory_descriptor(tmp_path,monkeypatch):
    from sandbox.azure_bootstrap import ensure_directory
    chown=[];monkeypatch.setattr('os.fchown',lambda fd,*args:chown.append(args))
    target=tmp_path/'workspace'/'cache';ensure_directory(str(target),owner=1000,mode=0o700)
    assert chown==[(1000,1000)] and target.stat().st_mode&0o777==0o700
