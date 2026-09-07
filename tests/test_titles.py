import asyncio,json
from datetime import datetime,timezone
import pytest
from chatkit.types import ThreadMetadata,UserMessageItem,UserMessageTextContent,AssistantMessageItem,AssistantMessageContent
from chatkit.store import NotFoundError
from backend.store import SQLiteStore
from backend.titles import Titles

@pytest.mark.asyncio
async def test_titles_use_opening_only_preserve_ownership_metadata_and_recency(tmp_path):
 store=SQLiteStore(tmp_path/'lab.db');context={'owner':'alice'}
 thread=ThreadMetadata(id='t1',created_at=datetime.now(timezone.utc))
 await store.save_thread(thread,context)
 user=UserMessageItem(id='u1',thread_id='t1',created_at=datetime.now(timezone.utc),content=[UserMessageTextContent(text='Build a Go counter')],inference_options={})
 response=AssistantMessageItem(id='a1',thread_id='t1',created_at=datetime.now(timezone.utc),content=[AssistantMessageContent(text='Built a counter with Add one')])
 await store.save_item('t1',user,context);await store.save_item('t1',response,context)
 next_user=user.model_copy(update={'id':'u2','content':[UserMessageTextContent(text='Later private context not used for the title')]})
 await store.save_item('t1',next_user,context)
 seen=[]
 async def completion(messages,**kwargs):
  seen.append((messages,kwargs));latest=await store.load_thread('t1',context);latest.metadata['coder_workspace_id']='new-claim';await store.save_thread(latest,context)
  return {'content':'{"t1":"Interactive Go Counter"}'}
 service=Titles(store,completion);entry=await service.opening('t1','alice')
 assert entry['user']=='Build a Go counter' and 'Later' not in json.dumps(entry)
 assert await service.generate([entry],'alice')==1
 latest=await store.load_thread('t1',context)
 assert latest.title=='Interactive Go Counter' and latest.metadata['coder_workspace_id']=='new-claim'
 before=store.db.execute('select updated from threads where id="t1"').fetchone()[0]
 assert not store.set_generated_title('t1','alice','A second title')
 assert store.db.execute('select updated from threads where id="t1"').fetchone()[0]==before
 with pytest.raises(NotFoundError):store.set_generated_title('t1','bob','Wrong owner')
 assert seen[0][1]['tools'] is False
 # An older in-flight thread save cannot undo a title produced in the background.
 thread.metadata['another_change']=True;await store.save_thread(thread,context)
 assert (await store.load_thread('t1',context)).title=='Interactive Go Counter'
 assert await service.opening('t1','alice') is None

@pytest.mark.asyncio
async def test_titles_wait_for_response_and_reject_bad_batch_without_partial_write(tmp_path):
 store=SQLiteStore(tmp_path/'lab.db');context={'owner':'alice'}
 for tid in ['t1','t2']:
  await store.save_thread(ThreadMetadata(id=tid,created_at=datetime.now(timezone.utc)),context)
  await store.save_item(tid,UserMessageItem(id='u'+tid,thread_id=tid,created_at=datetime.now(timezone.utc),content=[UserMessageTextContent(text='A new question')],inference_options={}),context)
 async def completion(*a,**kw):return {'content':'{"t1":"A useful title","t2":null}'}
 service=Titles(store,completion)
 assert await service.opening('t1','alice') is None
 entries=[await service.opening(t,'alice',allow_incomplete=True) for t in ['t1','t2']]
 with pytest.raises(ValueError):await service.generate(entries,'alice')
 assert (await store.load_thread('t1',context)).title is None

@pytest.mark.asyncio
async def test_history_recency_changes_for_new_message_not_item_replacement(tmp_path):
 store=SQLiteStore(tmp_path/'lab.db');c={'owner':'alice'}
 for tid in ['old','new']:await store.save_thread(ThreadMetadata(id=tid,created_at=datetime.now(timezone.utc)),c)
 item=UserMessageItem(id='u',thread_id='old',created_at=datetime.now(timezone.utc),content=[UserMessageTextContent(text='Continue here')],inference_options={})
 await store.save_item('old',item,c)
 assert (await store.load_threads(10,None,'desc',c)).data[0].id=='old'
 before=store.db.execute('select updated from threads where id="old"').fetchone()[0]
 await store.save_item('old',item,c)
 assert store.db.execute('select updated from threads where id="old"').fetchone()[0]==before
