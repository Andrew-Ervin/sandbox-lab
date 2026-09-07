import json
from datetime import datetime, timezone
import httpx, pytest
from chatkit.types import ThreadMetadata
from backend.chat import LabChat
from backend.citations import source_annotations
from backend.store import SQLiteStore


def citation(url='https://doc.rust-lang.org/cargo/',end=4):
    return {'type':'url_citation','url_citation':{'url':url,'title':'Cargo documentation','content':'Reference','end_index':end}}


def test_citations_validate_sources_and_preserve_native_positions():
    entries=[citation(),citation(),citation('javascript:alert(1)'),citation('https://secret@example.org'),citation('https://example.org/\n'),citation(end=999),{'type':'file_citation'},None]
    result=source_annotations('Read this.',entries)
    assert len(result)==2
    assert [r.index for r in result]==[4,None]
    assert result[0].source.type=='url' and result[0].source.title=='Cargo documentation'
    assert source_annotations('Text',None)==[]


@pytest.mark.asyncio
async def test_search_is_exa_admin_controlled_and_never_used_for_titles(monkeypatch):
    import backend.chat as module
    calls=[]
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'Read this.','annotations':[citation()]}}]})
    monkeypatch.setattr(module,'API_KEY','synthetic')
    monkeypatch.setenv('LAB_ALLOW_WEB_SEARCH','true')
    chat=LabChat(SQLiteStore(':memory:'));chat.http=httpx.AsyncClient(transport=httpx.MockTransport(respond))
    response=await chat.completion([{'role':'user','content':'Search Cargo documentation.'}])
    search=[t for t in calls[-1]['tools'] if t['type']=='openrouter:web_search']
    assert search[0]['parameters']['engine']=='exa' and calls[-1]['max_tool_calls']==2
    assert response['annotations']==[citation()]
    await chat.completion([],tools=False,max_tokens=40)
    assert 'tools' not in calls[-1] and 'max_tool_calls' not in calls[-1]
    await chat.completion([],tools=False,search=True)
    assert [t['type'] for t in calls[-1]['tools']]==['openrouter:web_search']
    monkeypatch.setenv('LAB_ALLOW_WEB_SEARCH','false')
    await chat.completion([])
    assert all(t['type']=='function' for t in calls[-1]['tools'])
    await chat.close()


@pytest.mark.asyncio
async def test_chatkit_response_and_reload_keep_native_citations(tmp_path,monkeypatch):
    store=SQLiteStore(tmp_path/'db');chat=LabChat(store);context={'owner':'test-owner'}
    await store.save_thread(ThreadMetadata(id='sources',title='Sources',created_at=datetime.now(timezone.utc)),context)
    async def completion(*args,**kwargs):return {'role':'assistant','content':'Read this.','annotations':[citation()]}
    monkeypatch.setattr(chat,'completion',completion)
    request={'type':'threads.add_user_message','params':{'thread_id':'sources','input':{'content':[{'type':'input_text','text':'Search Cargo docs'}],'attachments':[],'inference_options':{}}}}
    response=await chat.process(json.dumps(request).encode(),context)
    events=[json.loads(chunk[6:]) async for chunk in response]
    message=next(e['item'] for e in events if e.get('item',{}).get('type')=='assistant_message')
    assert message['content'][0]['annotations'][0]['source']['type']=='url'
    page=await store.load_thread_items('sources',None,10,'asc',context)
    saved=next(i for i in page.data if i.type=='assistant_message')
    assert saved.content[0].annotations[0].source.url=='https://doc.rust-lang.org/cargo/'
    assert not store.projects('test-owner')
    await chat.close()
