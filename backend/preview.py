"""A separate preview origin. Never forwards cookies or control-plane credentials."""
import asyncio,base64,hashlib,httpx,mimetypes,secrets,time
from urllib.parse import urljoin,urlsplit
from fastapi import FastAPI,Request,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import Response, JSONResponse
from .image_view import render as render_image
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
# One isolated app per localhost port, with capability-scoped asset URLs.
targets={}

def upstream_client(target):
    # Keep the fixed tunnel connection hot, without a response cookie jar.
    from http.cookiejar import DefaultCookiePolicy
    class NoCookies(DefaultCookiePolicy):
        def set_ok(self,*args,**kwargs):return False
        def return_ok(self,*args,**kwargs):return False
    client=target.get('http_client')
    if client is None:
        client=httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False,
            limits=httpx.Limits(max_connections=24,max_keepalive_connections=12,keepalive_expiry=60))
        client.cookies.jar.set_policy(NoCookies())
        target['http_client']=client
    return client
from .identity import identity
ARTIFACT_CSP="sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' blob:; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'"
from .preview_bridge import BRIDGE as ACTIVITY
_BRIDGE_HASH=base64.b64encode(hashlib.sha256(ACTIVITY.removeprefix(b'<script>').removesuffix(b'</script>')).digest()).decode()
DOCUMENT_CSP="sandbox allow-scripts; default-src 'none'; script-src 'sha256-"+_BRIDGE_HASH+"'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'"
APP_CSP="sandbox allow-scripts allow-forms; default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-src 'none'; object-src 'none'"

def app_path(target, path, request):
    """Authorize opaque app frames by an unguessable, preview-scoped path."""
    capability=target.get('capability','')
    prefix='_lab/'+capability
    if not capability:return None
    if path==prefix:return ''
    if path.startswith(prefix+'/'):return path[len(prefix)+1:]
    referer=request.headers.get('referer','')
    origin=f'http://127.0.0.1:{request.url.port}/{prefix}/'
    return path if referer.startswith(origin) else None

def ide_redirect(location, path, port):
    # code-server uses relative ./?folder= redirects on first open. Resolve only
    # local paths; absolute URLs, protocol-relative URLs and backslashes stay denied.
    parts=urlsplit(location)
    if not location or parts.scheme or parts.netloc or location.startswith('//') or '\\' in location or any(ord(c)<32 for c in location):return None
    origin=f'http://127.0.0.1:{port}'
    result=urlsplit(urljoin(origin+'/'+path,location))
    if result.scheme!='http' or result.netloc!=f'127.0.0.1:{port}':return None
    return (result.path or '/')+('?' + result.query if result.query else '')+('#'+result.fragment if result.fragment else '')
@app.api_route('/{path:path}',methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'])
async def preview(path:str,request:Request):
    port=request.url.port
    target=targets.get(port)
    if not target or target['expires']<time.time(): raise HTTPException(410,'Preview expired')
    if target.get('kind')=='app':
        path=app_path(target,path,request)
        if path is None:raise HTTPException(404,'Preview not found')
    else:
        await identity.authenticate(request.cookies.get('lab_session', ''))
        if not identity.preview_allowed(target,request.cookies):raise HTTPException(404,'Preview not found')
    if request.headers.get('host')!=f'127.0.0.1:{port}': raise HTTPException(403)
    common={'Content-Security-Policy':APP_CSP.replace("connect-src 'self'",f"connect-src 'self' ws://127.0.0.1:{port}"),'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cache-Control':'no-store','Access-Control-Allow-Origin':'null'}
    if target['kind']=='ide':
        # VS Code's service worker resolves virtual resource URLs locally. Their
        # encoded authorities contain '+', which CSP host-source cannot express
        # literally. Restrict the standard virtual host class to installed editor
        # assets; workspace files and arbitrary external hosts remain excluded.
        virtual_files='https://*.vscode-resource.vscode-cdn.net/home/sandbox/.local/share/code-server/extensions/'
        common['Content-Security-Policy']=f"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: {virtual_files}; style-src 'self' 'unsafe-inline' {virtual_files}; img-src 'self' data: blob: https://github.com https://raw.githubusercontent.com https://cdn.jsdelivr.net https://user-images.githubusercontent.com https://private-user-images.githubusercontent.com {virtual_files}; font-src 'self' data: {virtual_files}; connect-src 'self' ws://127.0.0.1:{port} {virtual_files}; worker-src 'self' blob:; frame-src 'self'; object-src 'none'; frame-ancestors 'self' http://127.0.0.1:3000 http://localhost:3000"
    if target['kind']=='ide' and path.startswith('__lab/marketplace-icons/'):
        # The browser may retrieve catalog icons only, never packages or arbitrary URLs.
        import re
        asset_path=path.removeprefix('__lab/marketplace-icons/')
        if request.method not in ('GET','HEAD') or not re.fullmatch(r'(?:remote/[a-f0-9]{64}|[A-Za-z0-9_.-]+)/Microsoft\.VisualStudio\.Services\.Icons\.Default',asset_path):raise HTTPException(404)
        from sandbox.editor_gallery import asset
        result=await asset(*asset_path.split('/',1))
        media_type='image/png' if result.body.startswith(b'\x89PNG\r\n\x1a\n') else result.media_type
        if not media_type or not media_type.startswith('image/'):raise HTTPException(404)
        return Response(result.body,media_type=media_type,headers={'Cache-Control':'private, max-age=3600','X-Content-Type-Options':'nosniff','Content-Security-Policy':"sandbox; default-src 'none'"})
    if target['kind']=='ide' and path=='__lab/editor-activity':
        if request.method!='POST' or request.headers.get('origin')!=f'http://127.0.0.1:{port}':raise HTTPException(403)
        from .azure_runtime import runtime
        from .previews import previews
        control=runtime();record=control.record(target['workspace_id'])
        if record['state']!='running':raise HTTPException(409,'Reopen this workspace to resume it')
        control.touch(record['id']);control.warm.demand('developer',record.get('compute_size'));previews.renew_workspace(record['id'])
        if time.time()-record.get('preferences_saved_at',0)>30:
            await control.editor_profiles.capture(record)
            record=control.record(record['id']);record['preferences_saved_at']=time.time();control.save(record)
        return JSONResponse({'active':True},headers=common)
    if target['kind']=='ide' and path=='__lab/editor-layout':
        if request.method!='POST' or request.headers.get('origin')!=f'http://127.0.0.1:{port}':raise HTTPException(403)
        raw=await request.body()
        if len(raw)>200000:raise HTTPException(413)
        from .azure_runtime import runtime
        from sandbox.editor_preferences import LAYOUT_KEYS
        try:
            layout=__import__('json').loads(raw)['layout']
            if not isinstance(layout,dict) or any(k not in LAYOUT_KEYS or not isinstance(v,str) or len(v)>16000 for k,v in layout.items()):raise ValueError()
        except (ValueError,KeyError,TypeError):raise HTTPException(400,'Invalid editor layout')
        owner=target.get('owner')
        if not owner:raise HTTPException(403)
        profiles=runtime().editor_profiles
        initial=await profiles.command(runtime().record(target['workspace_id']),{'action':'export'}) if profiles.get(owner)['profile'] is None else {}
        async with profiles.locks.setdefault(owner,asyncio.Lock()):
            current=profiles.get(owner)['profile'] or initial
            current['layout']=layout
            with runtime().db:runtime().db.execute('INSERT OR REPLACE INTO editor_profiles VALUES (?,?,?)',(owner,__import__('json').dumps(current),time.time()))
        return JSONResponse({'saved':True},headers=common)
    if request.method=='OPTIONS': return Response(headers={**common,'Access-Control-Allow-Methods':'GET,HEAD,POST,PUT,PATCH,DELETE,OPTIONS','Access-Control-Allow-Headers':'content-type'})
    if target['kind'] in ('artifact','document'):
        if path: raise HTTPException(404)
        common['Content-Security-Policy']=ARTIFACT_CSP
        content=target['content'] if target['kind']=='document' else target['path'].read_bytes();media=target['media_type']
        name=target['name'] if target['kind']=='document' else target['path'].name
        if target['kind']=='document':
            from .approval_view import render
            common['Content-Security-Policy']=DOCUMENT_CSP
            content=render(content,name);media='text/html'
        elif media.startswith('image/'):
            content=render_image(content,name,media);media='text/html'
        elif media!='text/html':
            from .file_view import render
            content=render(content,name);media='text/html'
        if media=='text/html':content+=ACTIVITY
        return Response(content,media_type=media,headers=common)
    allowed_origins={f'http://127.0.0.1:{port}'}
    if target['kind']=='app':allowed_origins.add('null')  # Opaque sandbox; capability path already authenticated.
    if request.method not in ('GET','HEAD') and request.headers.get('origin') not in allowed_origins:raise HTTPException(403,'Untrusted preview origin')
    raw=await request.body()
    if len(raw)>2_000_000: raise HTTPException(413)
    # Fixed loopback destination from our own Azure port forward; never a user URL.
    url=f'http://127.0.0.1:{target["upstream_port"]}/{path}'
    if request.url.query: url+='?'+request.url.query
    forwarded={'content-type':request.headers.get('content-type','application/octet-stream')}
    if target['kind']=='ide':
        forwarded['host']=f'127.0.0.1:{port}'
        forwarded['accept']=request.headers.get('accept','*/*')
    try:
        async with upstream_client(target).stream(request.method,url,content=raw,headers=forwarded) as r:
            body=bytearray()
            async for chunk in r.aiter_bytes():
                body.extend(chunk)
                if len(body)>20_000_000: raise HTTPException(413)
    except httpx.HTTPError: return Response('The app is starting. Try opening it again shortly.',status_code=503,media_type='text/plain',headers=common)
    if 300<=r.status_code<400:
        location=r.headers.get('location','')
        safe=ide_redirect(location,path,port) if target['kind']=='ide' else None
        if safe:
            return Response(status_code=r.status_code,headers={**common,'Location':safe})
        # Do not let generated redirects move the user onto the trusted app origin.
        return Response('Preview redirects are disabled in this lab.',status_code=409,media_type='text/plain',headers=common)
    if target['kind']=='ide' and path=='_static/out/browser/serviceWorker.js' and r.status_code==200:
        common['Service-Worker-Allowed']='/'
    if target['kind']=='ide' and 'text/html' in r.headers.get('content-type','') and path in ('','/'):
        from .config import ROOT
        from .azure_runtime import runtime
        from sandbox.editor_preferences import LAYOUT_KEYS
        profile=runtime().editor_profiles.get(target.get('owner',''))['profile'] or {}
        code=(ROOT/'sandbox/editor_layout.js').read_text().replace('__LAB_PROFILE__',__import__('json').dumps(profile.get('layout',{})).replace('<','\\u003c')).replace('__LAB_KEYS__',__import__('json').dumps(sorted(LAYOUT_KEYS)))
        code += '\n' + (ROOT/'sandbox/editor_marketplace_images.js').read_text()
        body=body.replace(b'<head>',b'<head><script>'+code.encode()+b'</script>',1)
    if target['kind']=='app':
        from .preview_assets import rewrite
        body=rewrite(body,r.headers.get('content-type',''),target['capability'])
    if target['kind']!='ide' and 'text/html' in r.headers.get('content-type',''):
        base=b'<base href="/_lab/'+target['capability'].encode()+b'/">'
        body=body.replace(b'<head>',b'<head>'+base,1)
        common['X-Lab-Revision']=hashlib.sha256(body).hexdigest()
        common['Access-Control-Expose-Headers']='X-Lab-Revision'
        body.extend(ACTIVITY.replace(b'let revision=null',b'let revision="'+common['X-Lab-Revision'].encode()+b'"'))
    return Response(bytes(body),status_code=r.status_code,media_type=r.headers.get('content-type','application/octet-stream'),headers=common)


@app.websocket('/{path:path}')
async def preview_socket(websocket:WebSocket,path:str):
    """HMR/app sockets stay on the fixed isolated workspace destination."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import WebSocketException
    port=websocket.url.port;target=targets.get(port)
    if target and target.get('kind') == 'ide':
        try: await identity.authenticate(websocket.cookies.get('lab_session', ''))
        except HTTPException:
            await websocket.close(code=1013); return
    if (not target or target.get('kind') not in ('app','ide') or target['expires']<time.time()
        or websocket.headers.get('host')!=f'127.0.0.1:{port}'
        or (target.get('kind')=='ide' and (not identity.preview_allowed(target,websocket.cookies) or websocket.headers.get('origin')!=f'http://127.0.0.1:{port}'))):
        await websocket.close(code=1008);return
    if target.get('kind')=='app':
        path=app_path(target,path,websocket)
        if path is None:
            await websocket.close(code=1008);return
    url=f'ws://127.0.0.1:{target["upstream_port"]}/{path}'
    if websocket.url.query:url+='?'+websocket.url.query
    protocols=[p.strip() for p in websocket.headers.get('sec-websocket-protocol','').split(',') if p.strip()]
    try:
        # No browser cookies, authorization, or control-plane credentials forwarded.
        async with connect(url,subprotocols=protocols or None,proxy=None,max_size=2_000_000,open_timeout=10) as upstream:
            await websocket.accept(subprotocol=upstream.subprotocol)
            async def incoming():
                while True:
                    event=await websocket.receive()
                    if event['type']=='websocket.disconnect':return
                    await upstream.send(event.get('text') if event.get('text') is not None else event['bytes'])
            async def outgoing():
                async for message in upstream:
                    if isinstance(message,str):await websocket.send_text(message)
                    else:await websocket.send_bytes(message)
            async def session_watch():
                while target['expires']>time.time() and (target.get('kind')=='app' or identity.preview_allowed(target,websocket.cookies)):await asyncio.sleep(10)
                await websocket.close(code=1008)
            tasks=[asyncio.create_task(incoming()),asyncio.create_task(outgoing()),asyncio.create_task(session_watch())]
            try:await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
    except (OSError,WebSocketDisconnect,WebSocketException):pass
    finally:
        try:await websocket.close()
        except (RuntimeError,WebSocketDisconnect):pass
