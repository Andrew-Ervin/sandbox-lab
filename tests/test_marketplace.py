import pytest
from sandbox.marketplace import safe_url,old_enough,read
from fastapi import HTTPException
import httpx

def test_registry_origins_and_age_fail_closed():
    assert safe_url('https://open-vsx.org/api/vendor/name/1/file/package.json')
    assert safe_url('https://openvsx.eclipsecontent.org/vendor/name/1/package.json')
    for url in ['http://open-vsx.org/api/a','https://open-vsx.org.evil/api/a','https://open-vsx.org/api/../secret','https://open-vsx.org/api/a?token=x','https://user@open-vsx.org/api/a','https://127.0.0.1/api/a','https://open-vsx.org/api/%2e%2e/a']:
        assert not safe_url(url)
    assert old_enough('2020-01-01T00:00:00Z')
    assert not old_enough('2999-01-01T00:00:00Z') and not old_enough('invalid')

@pytest.mark.asyncio
async def test_redirect_does_not_escape_registry():
    seen=[]
    def handle(req):seen.append(str(req.url));return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(HTTPException):await read(client,'https://open-vsx.org/api/example',100)
    assert len(seen)==1

@pytest.mark.asyncio
async def test_editor_constructed_asset_uri_and_platform_query(tmp_path,monkeypatch):
    monkeypatch.setenv("PACKAGE_CACHE",str(tmp_path/"packages"))
    from sandbox import marketplace,editor_gallery,package_gateway
    from fastapi import FastAPI
    monkeypatch.setenv('LAB_EDITOR_MARKETPLACE','true');monkeypatch.setenv('LAB_EDITOR_CACHE',str(tmp_path))
    actual_client=httpx.AsyncClient
    async def handle(req):
        if req.method=='POST':return httpx.Response(200,json={'results':[{'extensions':[{'publisher':{'publisherName':'vendor'},'extensionName':'theme','versions':[{'version':'1','lastUpdated':'2020-01-01T00:00:00Z','targetPlatform':'universal','files':[{'assetType':'Microsoft.VisualStudio.Code.Manifest','source':'https://open-vsx.org/api/vendor/theme/1/file/package.json'},{'assetType':'Microsoft.VisualStudio.Services.VSIXPackage','source':'https://open-vsx.org/api/vendor/theme/1/file/theme.vsix'}]}]}]}]})
        return httpx.Response(200,json={'name':'theme'})
    monkeypatch.setattr(marketplace.httpx,'AsyncClient',lambda **kw:actual_client(transport=httpx.MockTransport(handle),**kw))
    result=await marketplace.query({'filters':[{}]},editor_gallery.BASE,set());version=result['results'][0]['extensions'][0]['versions'][0]
    path=version['assetUri'].replace('http://127.0.0.1:3128','')+'/Microsoft.VisualStudio.Code.Manifest?targetPlatform=universal'
    app=FastAPI();app.include_router(editor_gallery.router);app.middleware('http')(package_gateway.readonly)
    monkeypatch.setattr(package_gateway,'save_catalog',lambda:None)
    async with actual_client(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        r=await client.get(path);assert r.status_code==200 and r.json()['name']=='theme'
        assert (await client.get(path+'&redirect=true&install=true')).status_code==200
        assert (await client.get(path+'&install=false')).status_code==403
        assert (await client.get(path+'&targetPlatform=universal')).status_code==403
        assert (await client.get(path+'&url=https://evil.example')).status_code==403
        assert (await client.get('/vscode/assets/remote/'+'0'*64+'/Microsoft.VisualStudio.Code.Manifest')).status_code==404

@pytest.mark.asyncio
async def test_readme_images_are_rasterized_and_redirects_stay_scoped():
    import io
    from PIL import Image
    from sandbox.marketplace_images import embed,allowed
    out=io.BytesIO();Image.new('RGB',(2,2),'red').save(out,format='PNG')
    seen=[]
    def handle(request):
        seen.append(str(request.url))
        if request.url.host=='github.com':return httpx.Response(302,headers={'location':'https://raw.githubusercontent.com/vendor/theme/main/hero.png'})
        return httpx.Response(200,content=out.getvalue())
    source=b'![Hero](https://github.com/vendor/theme/raw/main/hero.png) [Link](https://example.com/page)'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result=await embed(source,client)
    assert b'data:image/png;base64,' in result and b'https://example.com/page' in result
    assert len(seen)==2
    for url in ['https://127.0.0.1/a.png','https://github.com/owner/repo/issues/a.png','https://raw.githubusercontent.com/a/b/c.svg','https://raw.githubusercontent.com/a/b/c.png?secret=x']:
        assert not allowed(url)
    def denied(request):return httpx.Response(302,headers={'location':'http://127.0.0.1/private.png'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(denied)) as client:
        assert await embed(source,client)==source

@pytest.mark.asyncio
async def test_browser_icon_route_requires_owner_and_rejects_other_assets(monkeypatch):
    import time
    from backend import preview
    from sandbox import editor_gallery
    from fastapi.responses import Response
    monkeypatch.setattr(preview.identity,'enabled',False)
    monkeypatch.setitem(preview.targets,61234,{'kind':'ide','expires':time.time()+60})
    calls=[]
    async def asset(identity,path):calls.append((identity,path));return Response(b'\x89PNG\r\n\x1a\n',media_type='application/octet-stream')
    monkeypatch.setattr(editor_gallery,'asset',asset)
    path='/__lab/marketplace-icons/remote/'+'a'*64+'/Microsoft.VisualStudio.Services.Icons.Default'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=preview.app),base_url='http://127.0.0.1:61234') as client:
        assert (await client.get(path+'?targetPlatform=universal')).status_code==200
        assert (await client.get(path.replace('Icons.Default','VSIXPackage'))).status_code==404
        monkeypatch.setattr(preview.identity,'enabled',True)
        assert (await client.get(path)).status_code==404
    assert len(calls)==1
