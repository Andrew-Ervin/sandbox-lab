"""Fixed-upstream model gateway. Capabilities expire, but are NOT Pi-only."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
try:
    from sandbox.model_policy import provider_policy, require_zdr, web_search_tool
except ModuleNotFoundError:
    from model_policy import provider_policy, require_zdr, web_search_tool

MAX_BODY = int(os.getenv('MODEL_MAX_BODY_BYTES','2000000'))
AUDIENCE = 'sandbox-lab-model'
secret = os.environ['LAB_TOKEN_SECRET'].encode()
if len(secret) < 32:
    raise RuntimeError('LAB_TOKEN_SECRET must contain at least 32 bytes')
key = os.environ['OPENROUTER_API_KEY']
model = os.environ['OPENROUTER_MODEL']
allow_search = os.getenv('LAB_ALLOW_WEB_SEARCH', 'true').lower() == 'true'


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=180, proxy=os.getenv("UPSTREAM_PROXY") or None, trust_env=False, follow_redirects=False,
                                limits=httpx.Limits(max_connections=64, max_keepalive_connections=16)) as upstream:
        app.state.upstream = upstream
        yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.exception_handler(HTTPException)
async def gateway_error(request, error):
    # OpenAI-compatible shape lets Pi show the actual safe error instead of 'no body'.
    return JSONResponse(status_code=error.status_code, content={'error': {
        'message': str(error.detail), 'type': 'gateway_error', 'code': 'lab_' + str(error.status_code)}},
        headers={'Cache-Control': 'no-store'})


def authorize(request):
    try:
        header = request.headers.get('authorization', '')
        if not header and request.headers.get('x-api-key'):
            header = 'Bearer ' + request.headers['x-api-key']
        if not header.startswith('Bearer ') or len(header) > 4096:
            raise ValueError()
        payload, signature = header[7:].split('.')
        expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        now = time.time()
        if not isinstance(data, dict) or data.get('aud') != AUDIENCE or data.get('model') != model:
            raise ValueError()
        if any(type(data.get(k)) is not int for k in ('iat', 'exp')):
            raise ValueError()
        if not (now - 3630 <= data['iat'] <= now + 30 and now < data['exp'] <= data['iat'] + 3600):
            raise ValueError()
        if not re.fullmatch(r'[a-f0-9]{32}', data.get('jti', '')):
            raise ValueError()
        if not isinstance(data.get('workspace'), str) or not 1 <= len(data['workspace']) <= 128:
            raise ValueError()
        return data
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise HTTPException(403, 'Invalid model capability') from None


def compatible_messages(messages):
    # Old Pi OpenAI sessions can replay provider-specific reasoning that prevents
    # ZDR routing. Omit it only from completed turns on the outbound request.
    # Keep visible/tool history and current-turn reasoning for tool continuation;
    # never rewrite saved sessions or strip other providers' signed thinking.
    if not model.startswith('openai/'):
        return messages
    last_user = max((i for i, message in enumerate(messages) if message['role'] == 'user'), default=-1)
    replay_fields = {'reasoning_details', 'reasoning', 'reasoning_content'}
    return [
        {k: v for k, v in message.items() if k not in replay_fields}
        if i < last_user and message['role'] == 'assistant' else message
        for i, message in enumerate(messages)
    ]


def prepare_body(body):
    if not isinstance(body, dict):
        raise HTTPException(400, 'Expected a JSON object')
    messages = body.get('messages')
    if not isinstance(messages, list) or not messages:
        raise HTTPException(400, 'Expected a non-empty messages array')
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in {'system', 'developer', 'user', 'assistant', 'tool'}:
            raise HTTPException(400, 'Invalid message')
        content = message.get('content')
        if content is not None and not isinstance(content, (str, list)):
            raise HTTPException(400, 'Invalid message content')
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    raise HTTPException(400, 'Invalid content part')
                if part.get('type') == 'text' and isinstance(part.get('text'), str):
                    continue
                # No provider-side fetching of attacker-controlled URLs.
                image = part.get('image_url')
                if part.get('type') == 'image_url' and isinstance(image, dict) and re.fullmatch(
                    r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+', str(image.get('url', ''))):
                    continue
                raise HTTPException(400, 'Only text and inline images are permitted')
    tools = body.get('tools', [])
    if not isinstance(tools, list) or len(tools) > 32:
        raise HTTPException(400, 'Invalid tools')
    tools = [t for t in tools if isinstance(t, dict) and t.get('type') == 'function' and isinstance(t.get('function'), dict)]
    allowed = {'messages', 'tool_choice', 'stream', 'temperature', 'top_p', 'stop', 'parallel_tool_calls'}
    result = {k: v for k, v in body.items() if k in allowed}
    result['messages'] = compatible_messages(messages)
    if 'stream' in result and type(result['stream']) is not bool:
        raise HTTPException(400, 'Invalid streaming option')
    result.update(model=model, max_tokens=16000,
                  reasoning={'effort': os.getenv('OPENROUTER_REASONING', 'xhigh')},
                  provider=provider_policy())
    # Search is an approved disclosure channel, not a DLP control. Admin can disable it.
    if allow_search:
        search_tool=web_search_tool()
        if search_tool:
            tools.append(search_tool)
            result['max_tool_calls'] = search_tool['parameters']['max_uses']
    if tools:
        result['tools'] = tools
    else:
        result.pop('tool_choice', None)
    return result


def prepare_native(body, protocol):
    """Allow local harness tools, never upstream URL fetching or server-side tools."""
    if not isinstance(body, dict):
        raise HTTPException(400, 'Expected a JSON object')
    def check(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'image_url', 'file_url', 'url'}:
                    if not isinstance(child, str) or not re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+', child):
                        raise HTTPException(400, 'Remote content is not permitted')
                if key in {'file_id', 'server_url'}:
                    raise HTTPException(400, 'Remote content is not permitted')
                check(child)
        elif isinstance(value, list):
            for child in value: check(child)
    field = 'input' if protocol == 'responses' else 'messages'
    content = body.get(field)
    if not isinstance(content, (str, list)) or not content:
        raise HTTPException(400, 'Missing conversation input')
    check(content)
    tools = body.get('tools', [])
    if not isinstance(tools, list) or len(tools) > 128:
        raise HTTPException(400, 'Invalid tools')
    for tool in tools:
        if not isinstance(tool, dict): raise HTTPException(400, 'Invalid tool')
        if protocol == 'responses':
            if tool.get('type') not in {'function', 'custom'}:
                raise HTTPException(400, 'Only local tools are permitted')
        elif tool.get('type', 'custom') != 'custom' or not isinstance(tool.get('name'), str):
            raise HTTPException(400, 'Only local tools are permitted')
    allowed = {field, 'instructions', 'system', 'tools', 'tool_choice', 'stream', 'parallel_tool_calls'}
    result = {k:v for k,v in body.items() if k in allowed}
    result.update(model=model, provider=provider_policy())
    if protocol == 'responses':
        result.update(store=False, max_output_tokens=16000,
                      reasoning={'effort': os.getenv('OPENROUTER_REASONING', 'xhigh')})
    else:
        result.update(max_tokens=16000)
    return result


@app.post('/v1/responses')
@app.post('/v1/messages')
@app.post('/v1/chat/completions')
async def completions(request: Request):
    claims = authorize(request)
    try:
        size = int(request.headers.get('content-length', '0'))
        if size < 0:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, 'Invalid content length') from None
    if size > MAX_BODY:
        raise HTTPException(413)
    raw = bytearray()
    try:
        async with asyncio.timeout(30):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_BODY:
                    raise HTTPException(413)
                raw.extend(chunk)
    except TimeoutError:
        raise HTTPException(408) from None
    try:
        protocol = request.url.path.rsplit('/', 1)[-1]
        body = prepare_body(json.loads(raw)) if protocol == 'completions' else prepare_native(json.loads(raw), protocol)
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(400, 'Invalid JSON') from None
    client = request.app.state.upstream
    try:
        upstream = await client.send(client.build_request(
            'POST', 'https://openrouter.ai/api/v1/' + ('chat/completions' if protocol == 'completions' else protocol), json=body,
            headers={'Authorization': 'Bearer ' + key, 'X-Title': 'Sandbox Lab'}), stream=True)
    except httpx.HTTPError as error:
        logging.getLogger('lab.model').warning('Model transport failure: %s',type(error).__name__)
        raise HTTPException(502, 'Model provider unavailable') from None
    if upstream.status_code >= 300:
        # Only fixed diagnostic categories/shape; never log prompt/provider error text.
        error_bytes=bytearray()
        async for part in upstream.aiter_bytes():
            if len(error_bytes)+len(part)>65536: break
            error_bytes.extend(part)
        description=error_bytes.decode('utf-8',errors='replace').lower()
        categories=[label for label,needle in [('privacy','data policy'),('zdr','zdr'),('context','context length'),('image','image'),('tools','tool'),('parameters','parameter'),('routing','endpoint'),('rate','rate limit')] if needle in description]
        logging.getLogger('lab.model').warning('Model provider rejected request: status=%s categories=%s fields=%s messages=%s tools=%s',upstream.status_code,','.join(categories),','.join(sorted(body)),len(body.get('messages', body.get('input', []))),len(body.get('tools',[])))
        await upstream.aclose()
        if 'privacy' in categories or 'zdr' in categories:
            raise HTTPException(403, 'OpenRouter could not route this request under the required privacy policy. No privacy setting was relaxed. Ask the administrator to check provider eligibility and saved-session compatibility.')
        raise HTTPException(502, 'Model provider rejected request')

    async def chunks():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
    return StreamingResponse(chunks(), media_type=upstream.headers.get('content-type', 'application/json'),
                             headers={'Cache-Control': 'no-store'})


@app.get('/healthz')
async def health():
    return {'ok': True}

STT_MODEL = 'microsoft/mai-transcribe-2'
MAX_AUDIO_BYTES = int(os.getenv('DICTATION_MAX_BYTES','10000000'))


def prepare_transcription(body):
    if not isinstance(body, dict) or body.get('format') not in {'webm','ogg','mp4','wav'}:
        raise HTTPException(400, 'Unsupported recording format')
    encoded=body.get('data')
    if not isinstance(encoded,str) or len(encoded)>((MAX_AUDIO_BYTES+2)//3)*4:
        raise HTTPException(413, 'Recording is too large')
    try: raw=base64.b64decode(encoded,validate=True)
    except ValueError: raise HTTPException(400,'Invalid recording') from None
    if not raw or len(raw)>MAX_AUDIO_BYTES: raise HTTPException(400,'Empty or oversized recording')
    return {'model':STT_MODEL,'input_audio':{'data':encoded,'format':body['format']},
            'response_format':'json','provider':provider_policy(speech=True)}


async def verify_transcription_privacy(client):
    if not require_zdr():
        return
    # STT ignores provider selection. Refuse unless every advertised endpoint is ZDR.
    try:
        endpoints,zdr=await asyncio.gather(
            client.get('https://openrouter.ai/api/v1/models/'+STT_MODEL+'/endpoints'),
            client.get('https://openrouter.ai/api/v1/endpoints/zdr'))
        endpoints.raise_for_status();zdr.raise_for_status()
        candidates=endpoints.json()['data']['endpoints']
        eligible={(e['model_id'],e['tag'],e['name']) for e in zdr.json()['data']}
        if not candidates or any((e['model_id'],e['tag'],e['name']) not in eligible for e in candidates):
            raise ValueError('Unverified endpoint')
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        raise HTTPException(503,'ZDR transcription eligibility could not be verified. Audio was not sent.') from None


@app.post('/v1/audio/transcriptions')
async def transcription(request: Request):
    claims=authorize(request)
    raw=bytearray()
    try:
        async with asyncio.timeout(20):
            async for chunk in request.stream():
                if len(raw)+len(chunk)>((MAX_AUDIO_BYTES+2)//3)*4+1024:raise HTTPException(413,'Recording is too large')
                raw.extend(chunk)
        body=prepare_transcription(json.loads(raw))
    except (ValueError,UnicodeError,RecursionError):raise HTTPException(400,'Invalid recording request') from None
    except TimeoutError:raise HTTPException(408,'Recording upload timed out') from None
    client=request.app.state.upstream
    await verify_transcription_privacy(client)
    try:
        response=await client.post('https://openrouter.ai/api/v1/audio/transcriptions',json=body,
            headers={'Authorization':'Bearer '+key,'X-Title':'Sandbox Lab Dictation'},timeout=75)
        response.raise_for_status()
        text=response.json().get('text')
        if not isinstance(text,str):raise ValueError('Missing transcript')
    except httpx.TimeoutException:
        raise HTTPException(504,'Transcription timed out. Please try again; audio was not saved locally.') from None
    except httpx.HTTPStatusError as exc:
        code=exc.response.status_code
        message={400:'The speech provider rejected the recording format. Reload VS Code to update dictation.',401:'Transcription credentials need operator attention.',402:'Transcription account credit is unavailable.',403:'Transcription access was refused.',413:'The speech provider rejected the recording size.',429:'The speech provider is busy or rate limited. Please retry shortly.'}.get(code,'The speech provider is temporarily unavailable. Please try again.')
        raise HTTPException(502,message+' Audio was not saved locally.') from None
    except (httpx.HTTPError,ValueError):
        raise HTTPException(502,'Transcription returned an invalid response. Please try again; audio was not saved locally.') from None
    return JSONResponse({'text':text},headers={'Cache-Control':'no-store'})
