import json,time
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from chatkit.types import ThreadMetadata,UserMessageItem,UserMessageTextContent
from backend.store import SQLiteStore
from backend.names import Names,PROMPT

@pytest.mark.asyncio
async def test_project_backfill_and_workspace_suggestion_do_not_change_history(tmp_path):
    store=SQLiteStore(tmp_path/'db');context={'owner':'alice'}
    thread=ThreadMetadata(id='thr_a',created_at=datetime.now(timezone.utc))
    await store.save_thread(thread,context)
    project=store.ensure_project(thread,'alice')
    await store.save_item(thread.id,UserMessageItem(id='msg_a',thread_id=thread.id,created_at=datetime.now(timezone.utc),content=[UserMessageTextContent(text='Build a supply chain optimizer')],inference_options={}),context)
    with store.db:store.db.execute('UPDATE projects SET developer_workspace_id=? WHERE id=?',('workspace-a',project['id']))
    before=store.db.execute('SELECT updated FROM threads').fetchone()[0]
    completion=AsyncMock(return_value={'content':json.dumps({project['id']:'Supply Chain Optimizer','workspace-a':'Supply Chain Studio'})})
    names=Names(store,completion,SimpleNamespace(record=lambda wid:{'name':'old','state':'stopped'}))
    await names.generate()
    assert store.get_project(project['id'],'alice')['name']=='Supply Chain Optimizer'
    assert names.suggestion('workspace-a')=='Supply Chain Studio'
    assert store.db.execute('SELECT updated FROM threads').fetchone()[0]==before
    assert not names.candidates()
    assert completion.call_args.kwargs['tools'] is False and completion.call_args.kwargs['search'] is False
    assert 'untrusted reference data' in PROMPT

@pytest.mark.asyncio
async def test_metadata_and_old_item_updates_do_not_promote_thread(tmp_path):
    store=SQLiteStore(tmp_path/'db');context={'owner':'alice'}
    thread=ThreadMetadata(id='thr_a',created_at=datetime.now(timezone.utc))
    await store.save_thread(thread,context)
    with store.db:store.db.execute('UPDATE threads SET updated=1 WHERE id=?',(thread.id,))
    thread.title='Renamed';await store.save_thread(thread,context)
    assert store.db.execute('SELECT updated FROM threads').fetchone()[0]==1
    item=UserMessageItem(id='msg_a',thread_id=thread.id,created_at=datetime.now(timezone.utc),content=[UserMessageTextContent(text='new message')],inference_options={})
    await store.save_item(thread.id,item,context)
    stamp=store.db.execute('SELECT updated FROM threads').fetchone()[0]
    assert stamp>1
    item.content=[UserMessageTextContent(text='display repair')]
    await store.save_item(thread.id,item,context)
    assert store.db.execute('SELECT updated FROM threads').fetchone()[0]==stamp
