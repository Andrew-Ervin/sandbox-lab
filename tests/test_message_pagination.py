import json
from datetime import datetime,timezone
import pytest
from chatkit.types import ThreadMetadata
from chatkit.store import NotFoundError
from backend.store import SQLiteStore

@pytest.mark.asyncio
async def test_message_pages_parse_only_requested_rows_and_support_both_directions(tmp_path,monkeypatch):
    import backend.store as module
    store=SQLiteStore(tmp_path/'db');ctx={'owner':'alice'}
    for tid in ['a','b']:await store.save_thread(ThreadMetadata(id=tid,created_at=datetime.now(timezone.utc)),ctx)
    template={'type':'assistant_message','thread_id':'a','created_at':datetime.now(timezone.utc).isoformat(),'content':[{'type':'output_text','text':'x'*2000}]}
    with store.db:
        store.db.executemany('INSERT INTO items VALUES(?,?,?,?)',[(f'm{i}','a',json.dumps({**template,'id':f'm{i}'}),i) for i in range(1000)])
        store.db.execute('INSERT INTO items VALUES(?,?,?,?)',('foreign','b',json.dumps({**template,'id':'foreign','thread_id':'b'}),1))
    original=module.ITEM;parsed=[]
    class Counting:
        def validate_json(self,raw):parsed.append(1);return original.validate_json(raw)
    monkeypatch.setattr(module,'ITEM',Counting())
    page=await store.load_thread_items('a',None,30,'desc',ctx)
    assert len(parsed)==30 and len(page.data)==30 and page.has_more and page.after=='m970'
    next_page=await store.load_thread_items('a',page.after,30,'desc',ctx)
    assert next_page.data[0].id=='m969' and len(parsed)==60
    tail=await store.load_thread_items('a','m998',30,'asc',ctx)
    assert [item.id for item in tail.data]==['m999'] and not tail.has_more
    for cursor in ['foreign','missing']:
        with pytest.raises(NotFoundError):await store.load_thread_items('a',cursor,30,'asc',ctx)
    with pytest.raises(NotFoundError):await store.load_thread_items('a',None,30,'asc',{'owner':'bob'})

@pytest.mark.asyncio
async def test_oversized_client_page_is_clamped_instead_of_failing(tmp_path):
    store=SQLiteStore(tmp_path/'db');ctx={'owner':'a'}
    await store.save_thread(ThreadMetadata(id='t',created_at=datetime.now(timezone.utc)),ctx)
    page=await store.load_thread_items('t',None,100000,'desc',ctx)
    assert page.data==[] and not page.has_more
    with pytest.raises(ValueError):await store.load_thread_items('t',None,-1,'desc',ctx)
