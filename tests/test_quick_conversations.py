import asyncio,json
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock
import pytest
from backend.azure_adapters import AzureQuick
from backend.identity import current_owner

@pytest.mark.asyncio
async def test_quick_reuses_owner_conversation_and_retains_successful_vm(tmp_path,monkeypatch):
    from backend import checkpoints
    from backend import files
    monkeypatch.setattr(checkpoints,'load',lambda tid:[])
    monkeypatch.setattr(checkpoints,'directory',lambda tid:tmp_path)
    monkeypatch.setattr(files,'inputs',lambda *args:[])
    records={};created=[]
    async def create(kind,name,**kw):
        created.append((name,kw['owner']))
        records.setdefault(name,{'id':name,'name':name})
        return records[name]
    rt=SimpleNamespace(create=create,record=lambda wid:records[wid],save=Mock(),touch=Mock(),stop=AsyncMock(),
        storage=SimpleNamespace(enabled=False),execute=AsyncMock(return_value={'exit_code':0,'stdout':json.dumps({'stdout':'ok'})}))
    q=object.__new__(AzureQuick);q.runtime=rt;q.slots=asyncio.Semaphore(10);q.thread_locks={};q.queued=q.executing=0
    store=SimpleNamespace(save_run=Mock())
    token=current_owner.set('alice')
    try:
        for tid in ['a','a','b']:await q.quick('print(1)',{'id':'r','thread_id':tid},store)
        current_owner.set('bob');await q.quick('print(1)',{'id':'r','thread_id':'a'},store)
    finally:current_owner.reset(token)
    assert created[0]==created[1] and created[0]!=created[2] and created[0]!=created[3]
    rt.stop.assert_not_awaited()
    assert q.executing==q.queued==0

@pytest.mark.asyncio
async def test_quick_execution_requires_owner():
    q=object.__new__(AzureQuick)
    token=current_owner.set(None)
    try:
        with pytest.raises(RuntimeError,match='signed-in'):await q.quick('pass',{'thread_id':'t'},None)
    finally:current_owner.reset(token)
