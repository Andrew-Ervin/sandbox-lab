import pytest
from backend.execution_intent import execution_intent

@pytest.mark.asyncio
@pytest.mark.parametrize('reply,expected',[('none','none'),('quick','quick'),('project','project'),('Sure, project','none'),('', 'none')])
async def test_routing_is_conservative_and_has_no_tools(reply,expected):
    async def complete(messages,**kwargs):
        assert kwargs['tools'] is False and kwargs['search'] is False
        assert 'pricing' in messages[0]['content']
        return {'content':reply}
    assert await execution_intent(complete,[{'role':'user','content':'Compare VM pricing'}])==expected

@pytest.mark.asyncio
async def test_routing_failure_does_not_authorize_compute():
    async def unavailable(*args,**kwargs):raise RuntimeError('offline')
    assert await execution_intent(unavailable,[])=='none'

@pytest.mark.asyncio
async def test_research_delegation_does_not_create_run_or_project(tmp_path,monkeypatch):
    import backend.chat as module
    from backend.store import SQLiteStore
    from chatkit.types import ThreadMetadata,UserMessageItem,UserMessageTextContent
    from datetime import datetime,timezone
    store=SQLiteStore(tmp_path/'db');now=datetime.now(timezone.utc)
    thread=ThreadMetadata(id='research',title='Research',created_at=now)
    context={'owner':'test'}
    await store.save_thread(thread,context)
    await store.save_item(thread.id,UserMessageItem(id='user',thread_id=thread.id,created_at=now,content=[UserMessageTextContent(text='Search for Azure VMs and their pricing')],attachments=[],inference_options={}),context)
    chat=module.LabChat(store)
    monkeypatch.setattr(module.compute.policy,'warm',lambda:None)
    from backend.azure_adapters import NoReserve
    monkeypatch.setattr(module.headless,'reserve',NoReserve())
    calls=[]
    async def complete(messages,**kwargs):
        calls.append(kwargs)
        if kwargs.get('tools') is False:return {'content':'none'}
        if kwargs.get('execution_tools') is False:return {'content':'Here is a researched comparison.'}
        return {'role':'assistant','content':None,'tool_calls':[{'id':'call','type':'function','function':{'name':'delegate_project','arguments':'{"task":"Fetch the pricing API","mode":"analysis"}'}}]}
    chat.completion=complete
    async def forbidden(*args,**kwargs):raise AssertionError('Research allocated compute')
    monkeypatch.setattr(module.headless,'run',forbidden)
    events=[e async for e in chat._respond(thread,None,context)]
    assert events and not store.runs('test')
    assert store.project_for_thread(thread.id,'test') is None
    assert calls[-1]['execution_tools'] is False
    await chat.close()


def test_quick_escalation_requires_a_real_failure_signal():
    from backend.execution_intent import needs_project
    assert needs_project({'exit_code':1,'stdout':"ModuleNotFoundError: No module named 'special'"})
    assert needs_project({'timed_out':True})
    assert not needs_project({'exit_code':0,'stdout':'ModuleNotFoundError: quoted example'})
    assert not needs_project({'exit_code':1,'stdout':'SyntaxError: invalid syntax'})

@pytest.mark.asyncio
async def test_multiple_documentation_calls_are_all_processed_in_order(tmp_path,monkeypatch):
    import json
    import backend.chat as module
    from backend.store import SQLiteStore
    from chatkit.types import ThreadMetadata,UserMessageItem,UserMessageTextContent
    from datetime import datetime,timezone
    store=SQLiteStore(tmp_path/'db');now=datetime.now(timezone.utc)
    thread=ThreadMetadata(id='batch',title='Batch',created_at=now);context={'owner':'test'}
    await store.save_thread(thread,context)
    await store.save_item(thread.id,UserMessageItem(id='user',thread_id=thread.id,created_at=now,content=[UserMessageTextContent(text='Explain these settings')],attachments=[],inference_options={}),context)
    monkeypatch.setattr(module.compute.policy,'warm',lambda:None)
    monkeypatch.setattr(module.headless.reserve,'request',lambda:None)
    seen=[]
    def read_documentation(topic):
        seen.append(topic);return {'topic':topic}
    monkeypatch.setattr(module,'read_documentation',read_documentation)
    chat=module.LabChat(store)
    async def complete(messages,**kwargs):
        results=[m for m in messages if m.get('role')=='tool']
        if results:
            assert [r['tool_call_id'] for r in results]==['call0','call1','call2','call3']
            return {'role':'assistant','content':'All four settings explained.'}
        return {'role':'assistant','tool_calls':[{'id':f'call{i}','type':'function','function':{'name':'read_documentation','arguments':json.dumps({'topic':str(i)})}} for i in range(4)]}
    chat.completion=complete
    events=[e async for e in chat._respond(thread,None,context)]
    assert seen==['0','1','2','3']
    assert not store.runs('test')
    assert any(getattr(getattr(e,'item',None),'content',None) and getattr(e.item.content[0],'text','')=='All four settings explained.' for e in events)
    await chat.close()
