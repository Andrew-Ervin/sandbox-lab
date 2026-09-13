"""Exercise history serialization in a fresh process, before SDK schema warming."""
import subprocess
import sys


def test_saved_history_serializes_before_any_live_message_is_constructed(tmp_path):
    code='''
import asyncio,json,sys
from datetime import datetime,timezone
from backend.store import SQLiteStore
from chatkit.types import ThreadMetadata
async def main():
    store=SQLiteStore(sys.argv[1]);context={'owner':'local-owner'}
    await store.save_thread(ThreadMetadata(id='thr_history',created_at=datetime.now(timezone.utc)),context)
    # Simulate a saved message. Constructing the SDK message class first can
    # hide the incomplete-schema serializer failure that happens after restart.
    raw={'id':'msg_saved','thread_id':'thr_history','type':'assistant_message','created_at':'2026-09-12T00:00:00Z','content':[{'type':'output_text','text':'Saved answer','annotations':[]}]}
    store.db.execute('INSERT INTO items VALUES (?,?,?,?)',('msg_saved','thr_history',json.dumps(raw),1));store.db.commit()
    page=await store.load_thread_items('thr_history',None,20,'asc',context)
    result=json.loads(page.model_dump_json(by_alias=True,exclude_none=True,context={'exclude_metadata':True}))
    assert result['data'][0]['content'][0]['text']=='Saved answer'
    assert not result['has_more']
asyncio.run(main())
'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path/'history.db')],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
