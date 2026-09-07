"""A separate preview origin. Never forwards cookies or control-plane credentials."""
import asyncio,base64,hashlib,httpx,mimetypes,secrets,time
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import Response
from .image_view import render as render_image
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
# One app per localhost port: relative assets resolve normally, with no path rewriting.
targets={}
ARTIFACT_CSP="sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' blob:; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'"
from .preview_bridge import BRIDGE as ACTIVITY
_BRIDGE_HASH=base64.b64encode(hashlib.sha256(ACTIVITY.removeprefix(b'<script>').removesuffix(b'</script>')).digest()).decode()
DOCUMENT_CSP="sandbox allow-scripts; default-src 'none'; script-src 'sha256-"+_BRIDGE_HASH+"'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'"
APP_CSP="sandbox allow-scripts allow-forms; default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-src 'none'; object-src 'none'"
@app.api_route('/{path:path}',methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'])
async def preview(path:str,request:Request):
    port=request.url.port
    target=targets.get(port)
    if not target or target['expires']<time.time(): raise HTTPException(410,'Preview expired')
    if request.headers.get('host')!=f'127.0.0.1:{port}': raise HTTPException(403)
    common={'Content-Security-Policy':APP_CSP,'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cache-Control':'no-store','Access-Control-Allow-Origin':'null'}
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
    raw=await request.body()
    if len(raw)>2_000_000: raise HTTPException(413)
    # Fixed loopback destination from our own Coder port forward; never a user URL.
    url=f'http://127.0.0.1:{target["upstream_port"]}/{path}'
    if request.url.query: url+='?'+request.url.query
    async with httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False) as c:
        try:
            async with c.stream(request.method,url,content=raw,headers={'content-type':request.headers.get('content-type','application/octet-stream')}) as r:
                body=bytearray()
                async for chunk in r.aiter_bytes():
                    body.extend(chunk)
                    if len(body)>20_000_000: raise HTTPException(413)
        except httpx.HTTPError: return Response('The app is not listening on port 3000 yet. Reload the preview after it starts.',status_code=503,media_type='text/plain',headers=common)
    if 300<=r.status_code<400:
        # Do not let generated redirects move the user onto the trusted app origin.
        return Response('Preview redirects are disabled in this lab.',status_code=409,media_type='text/plain',headers=common)
    if 'text/html' in r.headers.get('content-type',''):body.extend(ACTIVITY)
    return Response(bytes(body),status_code=r.status_code,media_type=r.headers.get('content-type','application/octet-stream'),headers=common)
