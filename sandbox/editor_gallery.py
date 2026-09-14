"""Read-only gallery of operator-approved, pinned editor extensions."""
import hashlib
import json
import os
import uuid
from pathlib import Path
from zipfile import ZipFile
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

router = APIRouter()
BASE = 'http://127.0.0.1:3128/vscode'
ROOT = Path(__file__).resolve().parents[1]
verified = {}


def entries():
    return json.loads((ROOT/'infra/editor-extensions.lock.json').read_text())['extensions']


def archive(entry):
    path = Path(os.getenv('LAB_EDITOR_CACHE', str(ROOT/'.local/azure-pilot/extensions'))) / entry['file']
    if not path.is_file():
        raise HTTPException(503, 'Approved extension is not cached; run scripts/download_editor_extensions.py')
    if datetime.fromisoformat(entry['published'].replace('Z','+00:00')) > datetime.now(timezone.utc)-timedelta(days=5):
        raise HTTPException(403, 'Extension release is younger than five days')
    stamp=(path.stat().st_mtime_ns,path.stat().st_size,entry['sha256'])
    if verified.get(entry['id']) != stamp:
        with path.open('rb') as file:
            if hashlib.file_digest(file,'sha256').hexdigest() != entry['sha256']:
                raise HTTPException(503, 'Approved extension checksum failed')
        verified[entry['id']]=stamp
    return path


@router.post('/vscode/gallery/extensionquery')
async def query(request: Request):
    raw=await request.body()
    if len(raw)>16000:raise HTTPException(413, 'Gallery query too large')
    try:
        body=json.loads(raw)
        criteria=[c for f in body.get('filters',[]) for c in f.get('criteria',[])]
    except (ValueError, TypeError, AttributeError):raise HTTPException(400, 'Invalid gallery query') from None
    result=[]
    for entry in entries():
        identity=str(uuid.uuid5(uuid.NAMESPACE_URL,entry['id']))
        text=(entry['id']+' '+entry['displayName']+' '+entry['description']).lower()
        if any(c.get('filterType')==10 and str(c.get('value','')).lower() not in text for c in criteria):continue
        ids=[str(c.get('value','')).lower() for c in criteria if c.get('filterType') in (4,7)]
        if ids and entry['id'] not in ids and identity not in ids:continue
        files=[{'assetType':kind,'source':f"{BASE}/assets/{entry['id']}/{name}"} for kind,name in [('Microsoft.VisualStudio.Services.VSIXPackage','vsix'),('Microsoft.VisualStudio.Code.Manifest','manifest'),('Microsoft.VisualStudio.Services.Icons.Default','icon')]]
        result.append({'extensionId':identity,'extensionName':entry['name'],'displayName':entry['displayName'],'shortDescription':entry['description'],
            'publisher':{'publisherId':str(uuid.uuid5(uuid.NAMESPACE_URL,entry['publisher'])),'publisherName':entry['publisher'],'displayName':entry['publisher'],'flags':'verified'},
            'flags':'validated, public','lastUpdated':entry['published'],'publishedDate':entry['published'],'releaseDate':entry['published'],
            'versions':[{'version':entry['version'],'targetPlatform':entry['platform'],'lastUpdated':entry['published'],'assetUri':f"{BASE}/assets/{entry['id']}",'fallbackAssetUri':f"{BASE}/assets/{entry['id']}",'files':files,
                'properties':[{'key':'Microsoft.VisualStudio.Code.Engine','value':entry['engine']}]}],'statistics':[],'categories':['AI','Chat']})
    from sandbox import marketplace
    if marketplace.enabled():
        remote=await marketplace.query(body,BASE,{e['id'].lower() for e in entries()})
        groups=remote.get('results') or []
        if groups:
            groups[0]['extensions']=result+groups[0].get('extensions',[])
        return remote
    total=len(result)
    first=(body.get('filters') or [{}])[0]
    try:
        page=max(1,int(first.get('pageNumber',1)));size=max(1,min(100,int(first.get('pageSize',100))))
    except (ValueError,TypeError):raise HTTPException(400,'Invalid gallery pagination') from None
    result=result[(page-1)*size:page*size]
    return {'results':[{'extensions':result,'pagingToken':None,'resultMetadata':[{'metadataType':'ResultCount','metadataItems':[{'name':'TotalCount','count':total}]}]}]}


@router.get('/vscode/assets/{identity}/{asset:path}')
async def asset(identity: str, asset: str):
    if identity=='remote':
        from sandbox.marketplace import asset as remote_asset
        return await remote_asset(asset)
    asset={'Microsoft.VisualStudio.Services.VSIXPackage':'vsix','Microsoft.VisualStudio.Code.Manifest':'manifest','Microsoft.VisualStudio.Services.Icons.Default':'icon'}.get(asset,asset)
    entry=next((e for e in entries() if e['id']==identity),None)
    if entry is None:raise HTTPException(404,'Extension is not approved in this gallery')
    path=archive(entry)
    if asset=='vsix':return FileResponse(path,media_type='application/octet-stream')
    if asset not in ('manifest','icon'):raise HTTPException(404)
    name='package.json' if asset=='manifest' else entry.get('icon')
    if not name:raise HTTPException(404)
    with ZipFile(path) as z:
        data=z.read('extension/'+name)
    return Response(data,media_type='application/json' if asset=='manifest' else ('image/svg+xml' if name.endswith('.svg') else 'image/png'))
