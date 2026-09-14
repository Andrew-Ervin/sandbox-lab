"""Broker-only Open VSX catalog; fixed origins, age gate and bounded reads."""
import asyncio
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from fastapi import HTTPException
from fastapi.responses import Response

slots=asyncio.Semaphore(2)

def enabled():return os.getenv('LAB_EDITOR_MARKETPLACE','false').lower()=='true'
def database():
    root=Path(os.getenv('LAB_EDITOR_CACHE','.local/azure-pilot/extensions'));root.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(root/'marketplace.sqlite');db.execute('CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY,url TEXT,published TEXT)');db.execute('CREATE TABLE IF NOT EXISTS aliases (id TEXT PRIMARY KEY,asset TEXT)');return db

def safe_url(url):
    p=urlsplit(url)
    return p.scheme=='https' and p.netloc in ('open-vsx.org','openvsx.eclipsecontent.org') and not p.query and not p.fragment and not any(x in p.path for x in ('..','\\','%')) and (p.netloc!='open-vsx.org' or p.path.startswith('/api/'))

def old_enough(value):
    try:return datetime.fromisoformat(value.replace('Z','+00:00'))<=datetime.now(timezone.utc)-timedelta(days=5)
    except (ValueError,TypeError,AttributeError):return False

async def read(client,url,limit):
    for _ in range(3):
        if not safe_url(url):raise HTTPException(403,'Registry asset origin denied')
        async with client.stream('GET',url) as response:
            if response.status_code in (301,302,303,307,308):url=response.headers.get('location','');continue
            if response.status_code!=200:raise HTTPException(502,'Registry asset unavailable')
            data=bytearray()
            async for chunk in response.aiter_bytes():
                if len(data)+len(chunk)>limit:raise HTTPException(413,'Registry asset too large')
                data.extend(chunk)
            return bytes(data),response.headers.get('content-type','application/octet-stream')
    raise HTTPException(502,'Too many registry redirects')

async def query(body,base,pinned):
    filters=body.get('filters') or [{}]
    if not isinstance(filters,list) or len(filters)>1:raise HTTPException(400,'One catalog filter is supported')
    first=filters[0]
    try:
        page=int(first.get('pageNumber',1));size=int(first.get('pageSize',20))
        if not 1<=page<=100 or not 1<=size<=100:raise ValueError()
    except (ValueError,TypeError):raise HTTPException(400,'Invalid catalog page') from None
    criteria=first.get('criteria',[])
    if not isinstance(criteria,list) or len(criteria)>20:raise HTTPException(400,'Invalid catalog criteria')
    for c in criteria:
        if not isinstance(c,dict) or not isinstance(c.get('value',''),str) or len(c.get('value',''))>200:raise HTTPException(400,'Invalid catalog criteria')
    # Do not forward arbitrary client properties or headers to the registry.
    payload={'filters':[{'criteria':criteria,'pageNumber':page,'pageSize':size}], 'flags':914}
    async with slots,httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False) as client:
        r=await client.post('https://open-vsx.org/vscode/gallery/extensionquery',json=payload)
        if r.status_code!=200 or len(r.content)>4_000_000:raise HTTPException(502,'Registry catalog unavailable')
        result=r.json();db=database()
        try:
            for group in result.get('results',[]):
                kept=[]
                for extension in group.get('extensions',[]):
                    ident=(extension.get('publisher',{}).get('publisherName','')+'.'+extension.get('extensionName','')).lower()
                    if ident in pinned:continue
                    versions=[]
                    for version in extension.get('versions',[]):
                        published=version.get('lastUpdated')
                        if not old_enough(published):continue
                        files=[]
                        group_id=hashlib.sha256((ident+'|'+version['version']+'|'+str(version.get('targetPlatform',''))+'|'+published).encode()).hexdigest()
                        for asset in version.get('files',[]):
                            url=asset.get('source','')
                            if not safe_url(url):continue
                            token=hashlib.sha256((url+'|'+published).encode()).hexdigest()
                            db.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?)',(token,url,published))
                            asset_type=asset['assetType']
                            if not re.fullmatch(r'[A-Za-z0-9.]{1,120}',asset_type):continue
                            db.execute('INSERT OR REPLACE INTO aliases VALUES (?,?)',(group_id+'/'+asset_type,token))
                            files.append({'assetType':asset_type,'source':base+'/assets/remote/'+group_id+'/'+asset_type})
                        if not any(a['assetType']=='Microsoft.VisualStudio.Services.VSIXPackage' for a in files):continue
                        version['files']=files
                        # All listed assets have broker URLs; deny fallback remote fetching.
                        version['assetUri']=base+'/assets/remote/'+group_id;version['fallbackAssetUri']=version['assetUri']
                        versions.append(version)
                    if versions:extension['versions']=versions;kept.append(extension)
                group['extensions']=kept
            db.commit()
        finally:db.close()
        return result

async def asset(token):
    if not enabled() or not re.fullmatch(r'[a-f0-9]{64}(?:/[A-Za-z0-9.]{1,120})?',token):raise HTTPException(404)
    db=database()
    try:
        if '/' in token:
            alias=db.execute('SELECT asset FROM aliases WHERE id=?',(token,)).fetchone()
            if alias is None:raise HTTPException(404,'Asset not in catalog')
            token=alias[0]
        row=db.execute('SELECT url,published FROM assets WHERE id=?',(token,)).fetchone()
    finally:db.close()
    if row is None:raise HTTPException(404,'Asset was not returned by the catalog')
    if not old_enough(row[1]):raise HTTPException(403,'Extension release is younger than five days')
    async with slots,httpx.AsyncClient(timeout=120,trust_env=False,follow_redirects=False) as client:
        data,kind=await read(client,row[0],100_000_000)
    return Response(data,media_type=kind,headers={'Cache-Control':'private, max-age=3600','X-Content-Type-Options':'nosniff'})
