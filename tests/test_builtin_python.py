import asyncio,base64,json
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock
import pytest
from backend.azure_budget import AzureBudget
from backend.builtin_python import BuiltinPython
from backend.identity import current_owner

def adapter(tmp_path):
 q=object.__new__(BuiltinPython);q.capacity=2;q.queued=q.executing=0;q.thread_locks={};q.slots=asyncio.Semaphore(2)
 b=AzureBudget(tmp_path/'budget.sqlite');b.db.execute('CREATE TABLE python_sessions(identifier TEXT PRIMARY KEY, started REAL, expires REAL, paid_hours INTEGER)')
 q.runtime=SimpleNamespace(telemetry=SimpleNamespace(event=Mock()),budget=b,profile=lambda k:{'group':'test'},storage=SimpleNamespace(enabled=False,save=AsyncMock()),transport=SimpleNamespace(call=AsyncMock(return_value={'stdout':'ok','exit_code':0,'artifacts':[],'checkpoint':{'files':[]}})))
 return q

def test_hourly_accounting_and_capacity(tmp_path,monkeypatch):
 q=adapter(tmp_path);clock=[10000.];monkeypatch.setattr('backend.builtin_python.time.time',lambda:clock[0])
 q.account('a');q.account('a')
 assert q.runtime.budget.status()['estimated_and_reserved_usd']==.03
 clock[0]+=300;q.account('a')
 assert q.runtime.budget.status()['estimated_and_reserved_usd']==.06
 q.account('b')
 with pytest.raises(RuntimeError,match='not executed'):q.account('c')
 clock[0]+=3500;q.account('c')
 assert q.runtime.budget.status()['estimated_and_reserved_usd']==.12

@pytest.mark.asyncio
async def test_owner_identity_and_no_ambiguous_replay(tmp_path,monkeypatch):
 q=adapter(tmp_path)
 from backend import checkpoints
 monkeypatch.setattr(checkpoints,'directory',lambda tid:tmp_path)
 monkeypatch.setattr(checkpoints,'load',lambda tid:[])
 monkeypatch.setattr(checkpoints,'save',lambda *args:{'files':0})
 monkeypatch.setattr('backend.builtin_python.inputs',lambda *args:[])
 store=SimpleNamespace(save_run=Mock());token=current_owner.set('alice')
 try:
  await q.quick('print(1)',{'thread_id':'a','id':'r'},store)
  ident=q.runtime.transport.call.call_args.kwargs['args']['identifier']
  current_owner.set('bob');q.runtime.transport.call.side_effect=TimeoutError('unknown outcome')
  with pytest.raises(TimeoutError):await q.quick('print(1)',{'thread_id':'a','id':'r2'},store)
  assert q.runtime.transport.call.call_args.kwargs['args']['identifier']!=ident
  assert q.runtime.transport.call.await_count==2
  assert q.executing==q.queued==0
 finally:current_owner.reset(token)

@pytest.mark.asyncio
async def test_unauthenticated_call_allocates_nothing(tmp_path):
 q=adapter(tmp_path);token=current_owner.set(None)
 try:
  with pytest.raises(RuntimeError,match='signed-in'):await q.quick('pass',{'thread_id':'x'},None)
  q.runtime.transport.call.assert_not_awaited()
 finally:current_owner.reset(token)

def test_pool_prompt_does_not_claim_custom_packages(monkeypatch):
 from backend.assistant_context import runtime_system,SYSTEM
 monkeypatch.setattr('backend.azure_runtime.runtime',lambda:SimpleNamespace(config={'builtin_session_endpoint':'configured'}))
 text=runtime_system(SYSTEM)
 assert '1 CPU, 4 GiB' in text and 'RDKit/ASE' not in text
 assert 'do not assume' in text
