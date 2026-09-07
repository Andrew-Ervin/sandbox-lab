import asyncio
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from chatkit.store import NotFoundError
from chatkit.types import ThreadMetadata
from backend.store import SQLiteStore
from backend.coding_sessions import CodingSessions
from backend.native_coder import collect_result

@pytest.mark.asyncio
async def test_independent_status_survives_observer_failure_and_stop_checks_identity(monkeypatch):
    import backend.coding_sessions as module
    monkeypatch.setattr(module,'configuration',lambda:{'api_prefix':'/chats'})
    store=SQLiteStore(':memory:')
    await store.save_thread(ThreadMetadata(id='t',created_at=datetime.now(timezone.utc),metadata={'native_coder_chat_id':'c','coder_workspace_id':'w'}),{'owner':'alice'})
    coder=SimpleNamespace(api=AsyncMock(return_value={'status':'running','workspace_id':'w','latest_build':{'status':'running'}}))
    sessions=CodingSessions(coder,store);sessions.seed()
    assert sessions.active_workspaces=={'w'}
    assert (await sessions.for_thread('t','alice'))['status']=='running'
    with pytest.raises(NotFoundError):await sessions.stop('t','bob','c')
    with pytest.raises(ValueError):await sessions.stop('t','alice','old-session')
    coder.api.side_effect=httpx.ReadError('disconnected')
    assert (await sessions.read('c','w',force=True))['status']=='unknown'
    assert sessions.active_workspaces=={'w'}
    coder.api.side_effect=None
    assert (await sessions.stop('t','alice','c'))['status']=='stopping_workspace'
    assert any(c.args==('POST','/api/v2/workspaces/w/builds') and c.kwargs.get('json')=={'transition':'stop'} for c in coder.api.call_args_list)
    assert 'c' in sessions.stops
    assert any(c.args==('POST','/chats/c/interrupt') for c in coder.api.call_args_list)
    coder.api.return_value={'status':'waiting','workspace_id':'w','latest_build':{'status':'stopped'}}
    assert not (await sessions.read('c','w',force=True))['active']
    assert not sessions.active_workspaces
    sessions.begin('c','w');assert 'c' not in sessions.stops

@pytest.mark.asyncio
async def test_coder_reads_retry_but_prompt_mutations_never_replay(monkeypatch):
    from backend.coder import CoderAgents
    coder=CoderAgents()
    once=AsyncMock(side_effect=[httpx.ReadError('closed'),{'status':'waiting'}])
    monkeypatch.setattr(coder,'_api_once',once)
    monkeypatch.setattr(asyncio,'sleep',AsyncMock())
    assert await coder.api('GET','/chat')=={'status':'waiting'}
    assert once.await_count==2
    once.reset_mock();once.side_effect=httpx.ReadError('closed')
    with pytest.raises(httpx.ReadError):await coder.api('POST','/chat/messages')
    assert once.await_count==1

@pytest.mark.asyncio
async def test_completed_execution_survives_artifact_read_failure(monkeypatch):
    monkeypatch.setattr(asyncio,'sleep',AsyncMock())
    coder=SimpleNamespace(collect_artifacts=AsyncMock(side_effect=TimeoutError()))
    saved=[]
    files,warning=await collect_result(coder,{}, {'status':'running'},SimpleNamespace(save_run=lambda r:saved.append(dict(r))))
    assert files==[] and 'Coding completed' in warning
    assert coder.collect_artifacts.await_count==2
    assert all(r['status']=='running' for r in saved)

@pytest.mark.asyncio
async def test_main_model_connection_retries_before_dispatch(monkeypatch):
    import backend.chat as module
    from backend.chat import LabChat
    monkeypatch.setattr(module,'API_KEY','synthetic')
    monkeypatch.setattr(asyncio,'sleep',AsyncMock())
    chat=LabChat(SQLiteStore(':memory:'))
    chat.http=SimpleNamespace(post=AsyncMock(side_effect=[httpx.ReadError('closed'),httpx.Response(200,json={'choices':[{'message':{'content':'Recovered'}}]})]))
    assert (await chat.completion([{'role':'user','content':'Hello'}],tools=False))['content']=='Recovered'
    assert chat.http.post.await_count==2
