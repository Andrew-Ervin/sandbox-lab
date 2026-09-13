import asyncio
import httpx
import pytest
from backend.model_stream import Accumulator, stream_response
from backend.completion_validation import response_problem


def test_split_code_reasoning_and_citations():
    activity = {}
    state = Accumulator(activity)
    state.add({'choices': [{'delta': {'reasoning_details': [{'index': 0, 'type': 'reasoning.summary', 'summary': 'Use a small '}]}}]})
    state.add({'choices': [{'delta': {'reasoning_details': [{'index': 0, 'type': 'reasoning.summary', 'summary': 'example.'}], 'tool_calls': [{'index': 0, 'id': 'call_1', 'function': {'name': 'run_python', 'arguments': '{"code":"'}}]}}]})
    state.add({'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': 'print(1)"}'}}]}, 'finish_reason': 'tool_calls'}]})
    assert activity['reasoning'] == 'Use a small example.'
    assert activity['phase'] == 'Writing Python code'
    choice = state.result()['choices'][0]
    assert response_problem(choice) is None
    assert choice['message']['tool_calls'][0]['function']['arguments'] == '{"code":"print(1)"}'
    state.add({'choices': [{'delta': {'content': 'Result', 'annotations': [{'type': 'url_citation'}]}}]})
    assert state.result()['choices'][0]['message']['annotations']


def test_encrypted_reasoning_is_not_displayed():
    activity = {}
    state = Accumulator(activity)
    state.add({'choices': [{'delta': {'reasoning_details': [{'type': 'reasoning.encrypted', 'data': 'opaque'}]}}]})
    assert not activity.get('reasoning')
    assert state.result()['choices'][0]['message']['reasoning_details'][0]['data'] == 'opaque'


def test_disconnected_stream_is_not_success():
    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={'content-type': 'text/event-stream'}, text='data: {"choices":[{"delta":{"content":"Partial"}}]}\n\n'))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.RemoteProtocolError):
                await stream_response(client, 'https://test.invalid', {}, {}, {})
    asyncio.run(run())

@pytest.mark.parametrize('reasoning', ['', 'Compare the candidates.'])
def test_completed_thinking_only_remains_with_reasoning(reasoning):
    from backend.chat import LabChat
    from backend.store import SQLiteStore
    from chatkit.types import ThreadMetadata
    from datetime import datetime, timezone
    async def run():
        chat=LabChat(SQLiteStore(':memory:'))
        async def complete(messages,activity=None,**kwargs):
            activity['reasoning']=reasoning
            return {'role':'assistant','content':'Result'}
        chat.completion=complete
        thread=ThreadMetadata(id='test',created_at=datetime.now(timezone.utc))
        events=[event async for event,result in chat.model_activity(thread,[]) if event]
        removed=[event for event in events if event.type=='thread.item.removed']
        assert bool(removed)==(not reasoning)
        if removed:assert removed[0].item_id==events[0].item.id
        await chat.close()
    asyncio.run(run())
