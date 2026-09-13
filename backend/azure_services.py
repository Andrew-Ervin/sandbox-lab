"""Reverse package/model services over the authenticated sandbox relay.

The headless route has no model service. Package requests use the existing
fixed-host, read-only, age-gated facade; no arbitrary HTTP proxy is introduced.
"""
import asyncio
import base64
import json
import os
import re
from contextlib import AsyncExitStack
from .config import ROOT, STATE

_packages = None


def packages():
    global _packages
    if _packages is None:
        os.environ['PACKAGE_CACHE'] = str(STATE/'azure-runtime/package-cache')
        os.environ['PACKAGE_POLICY'] = str(ROOT/'infra/packages.json')
        from sandbox import package_gateway
        package_gateway.BASE = 'http://127.0.0.1:3128'
        _packages = package_gateway.app
    return _packages


def model_reservation(runtime, body):
    prices = runtime.config.get('model_prices', {})
    from .config import MODEL
    selected=body.get('model',MODEL)
    from .workspace_models import price
    try:prices=price(selected)
    except RuntimeError:
        if prices.get('model')!=selected or not prices.get('prompt') or not prices.get('completion'):
            raise RuntimeError('Verify current prices for the selected model before calling it.')
    # UTF-8 bytes bound input tokens conservatively; include protocol overhead.
    field = 'max_output_tokens' if 'max_output_tokens' in body else 'max_tokens'
    maximum = min(32768, int(body.get(field, 32768)))
    if maximum <= 0: raise ValueError('Invalid model output limit')
    body[field] = maximum
    # Cover approved server-side search as well as text inference.
    search = .10 if body.get('max_tool_calls') else 0
    return (len(json.dumps(body).encode())+8192)*float(prices['prompt']) + maximum*float(prices['completion']) + .05 + search + float(prices.get('request',0))


async def serve(runtime, record, ready=None):
    import httpx
    from websockets.asyncio.client import connect
    slots = asyncio.Semaphore(2)
    async with AsyncExitStack() as stack:
        package_client = await stack.enter_async_context(httpx.AsyncClient(transport=httpx.ASGITransport(app=packages()), base_url='http://packages', timeout=240))
        model_client = None
        if record['kind'] == 'developer':
            from sandbox import gateway
            from .workspace_models import resolve
            gateway.catalog_resolver=resolve
            await stack.enter_async_context(gateway.lifespan(gateway.app))
            model_client = await stack.enter_async_context(httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app), base_url='http://models', timeout=240))
        url = record['bridge_url'].replace('https://','wss://')+'/services'
        async with connect(url, additional_headers={'Authorization':'Bearer '+record['bridge_token']}, proxy=None,
                           max_size=3_000_000, max_queue=8, compression=None) as connection:
            acknowledgement = json.loads(await asyncio.wait_for(connection.recv(), 15))
            if acknowledgement != {'type': 'ready'}: raise RuntimeError('Sandbox service connection was not accepted')
            if ready:ready.set()
            async def handle(request):
                ident = request.get('id','')
                if not re.fullmatch('[a-f0-9]{32}',ident): return
                async def send(value): await connection.send(json.dumps({'id':ident,**value}))
                async with slots:
                    charge = None
                    model_active=False
                    try:
                        path = request['path']
                        if not path.startswith('/') or path.startswith('//') or len(path)>4096 or '\\' in path:
                            raise ValueError('Invalid service path')
                        if request['service'] == 'package':
                            gallery_query=request['method']=='POST' and path=='/vscode/gallery/extensionquery'
                            if gallery_query:
                                raw=base64.b64decode(request.get('body',''),validate=True)
                                if len(raw)>16000:raise ValueError('Gallery query too large')
                                response=await package_client.post(path,content=raw,headers={'content-type':'application/json'})
                            elif request['method'] != 'GET' or request.get('body') or not re.match(r'^/(python/|npm/|cargo/|go/|nuget/|julia/|artifact/|vscode/assets/)',path):
                                raise ValueError('Package request denied')
                            else:response = await package_client.get(path)
                        elif request['service'] == 'model' and model_client:
                            if (request['method'],path) not in (('POST','/v1/chat/completions'),('POST','/v1/responses'),('POST','/v1/messages'),('GET','/v1/models')): raise ValueError('Model route denied')
                            raw = base64.b64decode(request['body'], validate=True)
                            if len(raw)>2_000_000: raise ValueError('Model request too large')
                            # The existing gateway validates expiry/signature. Also
                            # bind this reverse connection to exactly its workspace.
                            from starlette.requests import Request
                            authorization = request.get('authorization','')
                            auth = gateway.authorize(Request({'type':'http','headers':[(b'authorization',authorization.encode())]}))
                            if auth['workspace'] != record['id']: raise ValueError('Workspace capability mismatch')
                            if path=='/v1/models':
                                models=auth.get('models',[auth['model']])
                                response=httpx.Response(200,json={'object':'list','models':[],'data':[{'id':item,'object':'model','owned_by':'lab'} for item in models]})
                                await send({'type':'headers','status':200,'content_type':'application/json'})
                                await send({'type':'body','data':base64.b64encode(response.content).decode()});await send({'type':'end'});return
                            runtime.touch(record['id']);runtime.warm.demand('developer',record.get('compute_size'))
                            runtime.active_commands[record['id']]=runtime.active_commands.get(record['id'],0)+1
                            model_active=True
                            from .previews import previews
                            previews.renew_workspace(record['id'])
                            protocol = path.rsplit('/', 1)[-1]
                            body = gateway.prepare_body(json.loads(raw),auth) if protocol == 'completions' else gateway.prepare_native(json.loads(raw), protocol,auth)
                            charge = runtime.budget.reserve('model',model_reservation(runtime,body))
                            response = await model_client.post(path,json=body,headers={'Authorization':authorization})
                        else: raise ValueError('Service denied')
                        if len(response.content)>250_000_000: raise ValueError('Service response too large')
                        await send({'type':'headers','status':response.status_code,'content_type':response.headers.get('content-type','application/octet-stream')})
                        for offset in range(0,len(response.content),65536):
                            await send({'type':'body','data':base64.b64encode(response.content[offset:offset+65536]).decode()})
                        await send({'type':'end'})
                    except Exception as error:
                        detail=str(error.detail) if hasattr(error,'detail') else str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__
                        runtime.telemetry.event(record['kind'],record['id'],'service_request_failed',error=detail[:250])
                        await send({'type':'headers','status':503,'content_type':'application/json'})
                        await send({'type':'body','data':base64.b64encode(b'{"error":{"message":"Broker service unavailable or request denied. Check runtime status and budget."}}').decode()})
                        await send({'type':'end'})
                    finally:
                        if model_active:
                            runtime.active_commands[record['id']]-=1
                            runtime.touch(record['id'])
                        # Keep the conservative maximum when a streaming gateway
                        # does not expose final billed usage. Never assume zero.
                        if charge: runtime.budget.finish(charge)
            pending = set()
            def completed(task):
                pending.discard(task)
                # Closing the workspace may disconnect a response already in
                # flight. Retrieve that failure; its budget remains reserved.
                if not task.cancelled(): task.exception()
            try:
                async for raw in connection:
                    if len(pending)>=16: raise RuntimeError('Sandbox service queue exceeded')
                    request = json.loads(raw)
                    task = asyncio.create_task(handle(request)); pending.add(task); task.add_done_callback(completed)
            finally:
                if ready: ready.clear()
                for task in pending: task.cancel()
                await asyncio.gather(*pending,return_exceptions=True)


async def tunnel(runtime, wid, remote_port, reader, writer):
    """One local TCP connection -> one authenticated fixed-port Azure socket."""
    from websockets.asyncio.client import connect
    record = runtime.record(wid)
    allowed = (3000,13337) if record['kind']=='developer' else (3000,)
    if remote_port not in allowed: raise ValueError('Port not available')
    url = record['bridge_url'].replace('https://','wss://')+f'/tcp/{remote_port}'
    try:
        async with connect(url, additional_headers={'Authorization':'Bearer '+record['bridge_token']},
                           proxy=None, max_size=2_000_000, compression=None) as connection:
            async def outgoing():
                while data := await reader.read(65536): await connection.send(data)
            async def incoming():
                async for data in connection:
                    if not isinstance(data,bytes): raise ValueError('Invalid tunnel data')
                    writer.write(data); await writer.drain()
            tasks = [asyncio.create_task(outgoing()),asyncio.create_task(incoming())]
            try: await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks: task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
    except Exception: pass
    finally:
        writer.close()
        try: await writer.wait_closed()
        except OSError: pass
