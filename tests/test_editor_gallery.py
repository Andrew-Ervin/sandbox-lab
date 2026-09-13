import hashlib
import json
from zipfile import ZipFile
import pytest
import httpx
from fastapi import FastAPI
from sandbox import editor_gallery


@pytest.mark.asyncio
async def test_gallery_only_exposes_approved_pins_and_rejects_tampered_archives(tmp_path, monkeypatch):
    path=tmp_path/'approved.vsix'
    with ZipFile(path,'w') as z:z.writestr('extension/package.json','{"name":"example"}')
    entry={'id':'vendor.example','publisher':'vendor','name':'example','displayName':'Example','description':'Reviewed example','version':'1.0.0','published':'2026-01-01T00:00:00Z','platform':'linux-x64','engine':'^1.94.0','file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    monkeypatch.setenv('LAB_EDITOR_CACHE',str(tmp_path));monkeypatch.setattr(editor_gallery,'entries',lambda:[entry])
    app=FastAPI();app.include_router(editor_gallery.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        r=await client.post('/vscode/gallery/extensionquery',json={'filters':[{'criteria':[{'filterType':10,'value':'example'}]}]})
        extension=r.json()['results'][0]['extensions'][0]
        assert extension['versions'][0]['version']=='1.0.0'
        assert (await client.get('/vscode/assets/vendor.other/vsix')).status_code==404
        assert (await client.get('/vscode/assets/vendor.example/manifest')).json()=={'name':'example'}
        next_page=await client.post('/vscode/gallery/extensionquery',json={'filters':[{'pageNumber':2,'pageSize':1}]})
        assert next_page.json()['results'][0]['extensions']==[]
        assert next_page.json()['results'][0]['resultMetadata'][0]['metadataItems'][0]['count']==1
        path.write_bytes(b'corrupt')
        assert (await client.get('/vscode/assets/vendor.example/vsix')).status_code==503
        assert (await client.post('/vscode/gallery/extensionquery',content=b'x'*16001)).status_code==413
