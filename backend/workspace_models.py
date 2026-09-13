"""Public model metadata; no credentials. Refresh before configuring a workstation."""
import asyncio
import hashlib
import json
import math
import time
import httpx
from .config import STATE, MODEL

_path=STATE/'workspace-model-catalog.json'
_lock=asyncio.Lock()
_catalog={}
_updated=0.0
_versions={}

def accept(data):
    result={}
    for entry in data:
        ident=entry.get('id',''); pricing=entry.get('pricing',{})
        try:
            prompt=float(pricing['prompt']); completion=float(pricing['completion'])
            request=float(pricing.get('request',0))
        except (KeyError,TypeError,ValueError):continue
        if not isinstance(ident,str) or not 1<=len(ident)<=160:continue
        if not all(math.isfinite(x) and x>=0 for x in (prompt,completion,request)):continue
        if 'text' not in entry.get('architecture',{}).get('output_modalities',['text']):continue
        result[ident]={**entry,'pricing':{**pricing,'prompt':prompt,'completion':completion,'request':request}}
    if MODEL not in result:raise ValueError('Default model absent from catalog')
    return result

async def refresh():
    global _catalog,_updated
    async with _lock:
        if _catalog and time.time()-_updated<3600:return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response=await client.get('https://openrouter.ai/api/v1/models');response.raise_for_status()
            catalog=accept(response.json()['data']);updated=time.time()
            _path.write_text(json.dumps({'updated':updated,'data':list(catalog.values())}));_path.chmod(0o600)
        except Exception:
            if not _path.exists():raise RuntimeError('Model catalog is unavailable; retry workspace setup') from None
            saved=json.loads(_path.read_text());updated=saved['updated'];catalog=accept(saved['data'])
            if time.time()-updated>86400:raise RuntimeError('Model prices are stale; retry workspace setup') from None
        _catalog=catalog;_updated=updated

def snapshot():
    if not _catalog or time.time()-_updated>86400:return None
    ids=sorted(_catalog)
    version=hashlib.sha256(json.dumps(ids).encode()).hexdigest()
    now=time.time()
    for old in list(_versions):
        if _versions[old][0]<=now:del _versions[old]
    _versions[version]=(now+3600,ids)
    return version,ids

def resolve(version):
    value=_versions.get(version)
    if value and value[0]>time.time():return value[1]
    current=snapshot()
    return current[1] if current and current[0]==version else None

def metadata():return list(_catalog.values())
def price(model):
    if snapshot() is None or model not in _catalog:raise RuntimeError('Current model prices are unavailable')
    return _catalog[model]['pricing']
