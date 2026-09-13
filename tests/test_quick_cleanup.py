import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from backend.quick_cleanup import QuickCleanup

@pytest.mark.asyncio
async def test_cleanup_returns_before_delete_and_recovers_failed_pending_work():
    state={'id':'one','kind':'quick','disposable':True,'state':'running','charge':'reserved'};gate=asyncio.Event();calls=[]
    async def stop(wid,delete):
        calls.append(wid);await gate.wait()
        if len(calls)==1:raise RuntimeError('Cloud unavailable')
        state.update(state='deleted');state.pop('charge')
    control=SimpleNamespace(record=lambda wid:dict(state),save=lambda r:state.update(r),stop=stop,records=lambda kind:[dict(state)],telemetry=SimpleNamespace(event=Mock()))
    q=QuickCleanup(control);q.schedule('one')
    assert state['cleanup_pending'] and state['charge']=='reserved'
    gate.set();await q.close()
    assert state['cleanup_pending'] and state['charge']=='reserved'
    state['cleanup_retry_at']=0;q.maintain();await q.close()
    assert state['state']=='deleted' and 'charge' not in state

@pytest.mark.asyncio
async def test_persistent_and_warm_workspaces_cannot_enter_disposable_cleanup():
    for record in [{'kind':'headless','disposable':True},{'kind':'quick','disposable':False},{'kind':'quick','disposable':True,'warm':True}]:
        q=QuickCleanup(SimpleNamespace(record=lambda wid:record))
        with pytest.raises(ValueError):q.schedule('one')
