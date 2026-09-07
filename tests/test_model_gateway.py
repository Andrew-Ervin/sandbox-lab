import base64
import copy
import hashlib
import hmac
import importlib.util
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request


@pytest.fixture(autouse=True)
def enforced_test_policy(monkeypatch):
    monkeypatch.setenv('OPENROUTER_REQUIRE_ZDR', 'true')
    monkeypatch.setenv('OPENROUTER_PROVIDER_ORDER', 'amazon-bedrock,openai')
    monkeypatch.setenv('OPENROUTER_PROVIDER_IGNORE', 'azure')
    monkeypatch.setenv('OPENROUTER_DATA_COLLECTION', 'deny')


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    monkeypatch.setenv('LAB_TOKEN_SECRET', 'test-signing-secret-for-unit-tests-only')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-provider-key')
    monkeypatch.setenv('OPENROUTER_MODEL', 'test/model')
    monkeypatch.setenv('LAB_MODEL_LEDGER', str(tmp_path / 'usage.db'))
    spec = importlib.util.spec_from_file_location('test_gateway', Path(__file__).parents[1] / 'sandbox/gateway.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def token(gateway, **updates):
    claims = dict(aud=gateway.AUDIENCE, iat=int(time.time()), exp=int(time.time()) + 120,
                  model=gateway.model, jti='a' * 32, calls=2, workspace='test-project')
    claims.update(updates)
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    signature = hmac.new(gateway.secret, payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def request(value):
    return Request({'type': 'http', 'headers': [(b'authorization', ('Bearer ' + value).encode())]})


def test_auth_binds_audience_expiry_and_model(gateway):
    assert gateway.authorize(request(token(gateway)))['workspace'] == 'test-project'
    for override in ({'aud': 'elsewhere'}, {'exp': 1}, {'exp': int(time.time()) + 7200},
                     {'iat': int(time.time()) + 300},
                     {'workspace': ''}, {'model': 'expensive-model'}, {'jti': []}):
        with pytest.raises(HTTPException) as error:
            gateway.authorize(request(token(gateway, **override)))
        assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        gateway.authorize(request(token(gateway) + 'tampered'))


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy_calls', [None, 1])
async def test_requests_do_not_exhaust_a_valid_credential(gateway, legacy_calls):
    async def upstream(req):return httpx.Response(200,json={'choices':[]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as provider:
        gateway.app.state.upstream=provider
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app),base_url='http://gateway') as client:
            headers={'Authorization':'Bearer '+token(gateway,calls=legacy_calls)}
            for _ in range(70):
                result=await client.post('/v1/chat/completions',headers=headers,json={'messages':[{'role':'user','content':'test'}]})
                assert result.status_code==200


def test_client_cannot_weaken_privacy_or_enable_other_search(gateway):
    body = gateway.prepare_body({'messages': [{'role': 'user', 'content': 'hello'}],
        'provider': {'zdr': False, 'data_collection': 'allow'}, 'model': 'other', 'max_tokens': 999999,
        'plugins': [{'id': 'web'}], 'tools': [{'type': 'openrouter:web_search', 'parameters': {'engine': 'other'}}]})
    assert body['provider'] == {'zdr': True, 'data_collection': 'deny', 'order': ['amazon-bedrock', 'openai'], 'ignore': ['azure'], 'allow_fallbacks': True}
    assert body['model'] == 'test/model' and body['max_tokens'] == 16000
    assert 'plugins' not in body
    assert body['tools'][0]['parameters']['engine'] == 'exa'
    gateway.allow_search = False
    body = gateway.prepare_body({'messages': [{'role': 'user', 'content': 'hello'}],
                                 'tools': [{'type': 'openrouter:web_search'}]})
    assert 'tools' not in body


def test_old_openai_reasoning_is_omitted_without_losing_tool_or_current_turn_history(gateway):
    gateway.model = 'openai/test-model'
    reasoning = {'reasoning_details': [{'type': 'reasoning.encrypted', 'data': 'opaque'}],
                 'reasoning': 'test reasoning', 'reasoning_content': 'test content'}
    messages = [
        {'role': 'user', 'content': 'Make a file'},
        {'role': 'assistant', 'content': None, **reasoning,
         'tool_calls': [{'id': 'first', 'type': 'function', 'function': {'name': 'write', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'first', 'content': 'File created'},
        {'role': 'assistant', 'content': 'Done', **reasoning},
        {'role': 'user', 'content': 'Read it again'},
        {'role': 'assistant', 'content': None, **reasoning,
         'tool_calls': [{'id': 'second', 'type': 'function', 'function': {'name': 'read', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'second', 'content': 'File contents'},
    ]
    original = copy.deepcopy(messages)
    body = gateway.prepare_body({'messages': messages})
    for i in (1, 3):
        assert not set(reasoning).intersection(body['messages'][i])
        assert body['messages'][i] == {k: v for k, v in original[i].items() if k not in reasoning}
    for i in (0, 2, 4, 5, 6):
        assert body['messages'][i] == original[i]
    assert messages == original  # no mutation of a saved Pi session
    assert body['provider'] == {'zdr': True, 'data_collection': 'deny', 'order': ['amazon-bedrock', 'openai'], 'ignore': ['azure'], 'allow_fallbacks': True}


@pytest.mark.parametrize('provider', ['anthropic/test-model', 'test/model', 'openai/test-model'])
def test_no_completed_turn_or_other_provider_reasoning_is_preserved(gateway, provider):
    gateway.model = provider
    messages = [{'role': 'assistant', 'content': 'result',
                 'reasoning_details': [{'type': 'reasoning.encrypted', 'data': 'signature'}]}]
    assert gateway.prepare_body({'messages': messages})['messages'] == messages
    if not provider.startswith('openai/'):
        messages.append({'role': 'user', 'content': 'Continue'})
        assert gateway.prepare_body({'messages': messages})['messages'] == messages


@pytest.mark.parametrize('body', [[], None, {'messages': []}, {'messages': [None]},
    {'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://outside.example/private'}}]}]},
    {'messages': [{'role': 'user', 'content': 'ok'}], 'tools': None}])
def test_invalid_or_remote_inputs_are_rejected(gateway, body):
    with pytest.raises(HTTPException): gateway.prepare_body(body)


@pytest.mark.asyncio
async def test_endpoint_bounds_chunked_input_and_forwards_privacy(gateway):
    seen = []
    async def upstream(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={'choices': []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as provider:
        gateway.app.state.upstream = provider
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app), base_url='http://gateway') as client:
            headers = {'Authorization': 'Bearer ' + token(gateway)}
            async def too_large():
                yield b' ' * 1_100_000
                yield b' ' * 1_100_000
            assert (await client.post('/v1/chat/completions', content=too_large(), headers=headers)).status_code == 413
            assert (await client.post('/v1/chat/completions', content=b'{', headers=headers)).status_code == 400
            r = await client.post('/v1/chat/completions', json={'messages': [{'role': 'user', 'content': 'test'}]}, headers=headers)
            assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
            assert seen[0]['provider']['zdr'] is True


@pytest.mark.asyncio
async def test_chat_and_titles_use_zdr(monkeypatch):
    from backend.chat import LabChat
    from backend.store import SQLiteStore
    seen = []
    async def upstream(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'title'}}]})
    chat = LabChat(SQLiteStore(':memory:'))
    monkeypatch.setattr('backend.chat.API_KEY', 'test-key')
    chat.http = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    try:
        await chat.completion([{'role': 'user', 'content': 'test'}], tools=False, max_tokens=40)
        assert seen[0]['provider'] == {'zdr': True, 'data_collection': 'deny', 'order': ['amazon-bedrock', 'openai'], 'ignore': ['azure'], 'allow_fallbacks': True}
    finally:
        await chat.close()

@pytest.mark.asyncio
async def test_provider_privacy_rejection_is_clear_and_never_retried_without_policy(gateway, caplog):
    seen=[]
    async def upstream(req):
        seen.append(json.loads(req.content))
        return httpx.Response(404,json={'error':{'message':'No endpoints matching data policy; private-provider-detail'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as provider:
        gateway.app.state.upstream=provider
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app),base_url='http://gateway') as client:
            r=await client.post('/v1/chat/completions',headers={'Authorization':'Bearer '+token(gateway)},json={'messages':[{'role':'user','content':'private-synthetic-input'}]})
            assert r.status_code==403
            assert 'privacy policy' in r.json()['error']['message']
            assert len(seen)==1 and seen[0]['provider']=={'zdr':True,'data_collection':'deny','order':['amazon-bedrock','openai'],'ignore':['azure'],'allow_fallbacks':True}
            assert 'private-provider-detail' not in r.text+caplog.text
            assert 'private-synthetic-input' not in r.text+caplog.text


def test_long_tool_session_has_no_message_count_ceiling(gateway):
    messages=[{'role':'user','content':'Continue'}]
    for i in range(1100):
        messages.extend([
            {'role':'assistant','content':None,'tool_calls':[{'id':f'call_{i}','type':'function','function':{'name':'read','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':f'call_{i}','content':'ok'},
        ])
    result=gateway.prepare_body({'messages':messages})
    assert result['messages']==messages

@pytest.mark.parametrize('protocol', ['responses','messages'])
def test_native_protocol_cannot_weaken_policy_or_enable_server_tools(gateway,protocol):
    field='input' if protocol=='responses' else 'messages'
    body={field:[{'role':'user','content':'hello'}],'model':'other','provider':{'zdr':False},'store':True,'previous_response_id':'other'}
    result=gateway.prepare_native(body,protocol)
    assert result['model']==gateway.model
    assert result['provider']=={'zdr':True,'data_collection':'deny','order':['amazon-bedrock','openai'],'ignore':['azure'],'allow_fallbacks':True}
    assert 'previous_response_id' not in result
    assert result.get('store',False) is False
    with pytest.raises(HTTPException):gateway.prepare_native({**body,'tools':[{'type':'web_search'}]},protocol)
    with pytest.raises(HTTPException):gateway.prepare_native({field:[{'type':'input_image','image_url':'https://unapproved.example/image'}]},protocol)


def test_dictation_bounds_and_fixed_model(gateway):
    result=gateway.prepare_transcription({'data':base64.b64encode(b'RIFFsynthetic').decode(),'format':'wav','model':'untrusted'})
    assert result['model']=='microsoft/mai-transcribe-2'
    assert result['provider']['zdr'] is True
    for body in [{'data':'!','format':'wav'},{'data':'','format':'wav'},{'data':'AAAA','format':'url'}]:
        with pytest.raises(HTTPException):gateway.prepare_transcription(body)

@pytest.mark.asyncio
async def test_dictation_fails_before_upload_if_any_endpoint_is_not_zdr(gateway):
    posted=[]
    endpoint={'model_id':gateway.STT_MODEL,'tag':'azure','name':'Azure test'}
    async def upstream(req):
        if req.method=='POST':posted.append(req)
        if req.url.path.endswith('/endpoints'):return httpx.Response(200,json={'data':{'endpoints':[endpoint]}})
        return httpx.Response(200,json={'data':[]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        with pytest.raises(HTTPException):await gateway.verify_transcription_privacy(client)
    assert not posted

@pytest.mark.asyncio
async def test_dictation_transcript_and_credentials_stay_server_side(gateway):
    seen=[];endpoint={'model_id':gateway.STT_MODEL,'tag':'azure','name':'Azure test'}
    async def upstream(req):
        if req.method=='GET':return httpx.Response(200,json={'data':{'endpoints':[endpoint]}} if req.url.path.endswith('/endpoints') else {'data':[endpoint]})
        seen.append(req);return httpx.Response(200,json={'text':'Hello world'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as provider:
        gateway.app.state.upstream=provider
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app),base_url='http://gateway') as client:
            body={'data':base64.b64encode(b'RIFFtest').decode(),'format':'wav'}
            assert (await client.post('/v1/audio/transcriptions',json=body)).status_code==403
            result=await client.post('/v1/audio/transcriptions',json=body,headers={'Authorization':'Bearer '+token(gateway)})
            assert result.json()=={'text':'Hello world'}
            assert result.headers['cache-control']=='no-store'
            assert len(seen)==1 and seen[0].headers['Authorization']=='Bearer test-provider-key'

@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected',[(400,'format'),(402,'credit'),(429,'rate limited'),(503,'temporarily unavailable')])
async def test_dictation_error_is_actionable_without_echoing_provider_payload(gateway,monkeypatch,status,expected):
    async def verified(client):pass
    monkeypatch.setattr(gateway,'verify_transcription_privacy',verified)
    async def provider(req):return httpx.Response(status,json={'error':{'message':'private provider content'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as upstream:
        gateway.app.state.upstream=upstream
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app),base_url='http://test') as c:
            r=await c.post('/v1/audio/transcriptions',headers={'Authorization':'Bearer '+token(gateway)},json={'format':'wav','data':base64.b64encode(b'RIFFsynthetic').decode()})
            assert r.status_code==502 and expected in r.text
            assert 'private provider content' not in r.text

def test_five_minute_wav_fits_upload_bound(gateway):
    assert 44+302*16000*2<=gateway.MAX_AUDIO_BYTES


@pytest.mark.asyncio
async def test_operator_can_temporarily_disable_zdr_without_client_routing_override(gateway, monkeypatch):
    monkeypatch.setenv('OPENROUTER_REQUIRE_ZDR', 'false')
    body = gateway.prepare_body({'messages':[{'role':'user','content':'test'}],
                                 'provider':{'only':['azure'],'zdr':True}})
    assert body['provider'] == {'zdr':False,'data_collection':'deny','order':['amazon-bedrock','openai'],'ignore':['azure'],'allow_fallbacks':True}
    assert gateway.prepare_native({'input':'hello'}, 'responses')['provider'] == body['provider']
    class NoRequests:
        async def get(self, *args): raise AssertionError('Disabled ZDR should not query metadata')
    await gateway.verify_transcription_privacy(NoRequests())
    from sandbox.model_policy import provider_policy
    assert provider_policy(speech=True) == {'zdr':False,'data_collection':'deny'}
    monkeypatch.setenv('OPENROUTER_REQUIRE_ZDR', 'typo')
    with pytest.raises(ValueError): provider_policy()
