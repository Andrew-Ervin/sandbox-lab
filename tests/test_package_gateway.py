import importlib.util,json,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx,pytest

@pytest.fixture
def gateway(tmp_path,monkeypatch):
    monkeypatch.setenv('PACKAGE_CACHE',str(tmp_path/'cache'))
    spec=importlib.util.spec_from_file_location('package_gateway',Path(__file__).parents[1]/'sandbox/package_gateway.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.CACHE=tmp_path/'cache';m.POLICY=tmp_path/'policy.json'
    m.POLICY.write_text(json.dumps({'minimum_age_days':5,'packages':{'python':['numpy'],'npm':['react'],'cargo':['serde'],'go':['example.com/module'],'julia':[]},'overrides':[]}))
    return m

@pytest.mark.asyncio
async def test_python_age_policy_filters_index_and_rechecks_artifacts(gateway,monkeypatch):
    m=gateway;now=datetime.now(timezone.utc);old=(now-timedelta(days=6)).isoformat();new=now.isoformat()
    data={'info':{'requires_dist':['approved-dependency>=1']},'releases':{'1.0':[{'upload_time_iso_8601':old,'url':'https://files.pythonhosted.org/old.whl','filename':'old.whl','digests':{'sha256':'a'*64}}],'2.0':[{'upload_time_iso_8601':new,'url':'https://files.pythonhosted.org/new.whl','filename':'new.whl','digests':{'sha256':'b'*64}}]}}
    calls=[]
    async def metadata(url):calls.append(url);return data
    monkeypatch.setattr(m,'metadata',metadata)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app),base_url='http://gateway') as c:
        assert (await c.get('/python/simple/package-not-in-any-list/')).status_code==200
        assert calls==['https://pypi.org/pypi/package-not-in-any-list/json']
        assert (await c.get('/python/simple/bad%3Aname/')).status_code==400
        r=await c.get('/python/simple/numpy/');assert r.status_code==200 and 'old.whl' in r.text and 'new.whl' not in r.text
        assert 'approved-dependency' in m.admitted['python']
        ident=next(iter(m.downloads));entry=m.downloads[ident];entry['published']=new;m.downloads[ident]=entry
        assert (await c.get('/artifact/'+ident)).status_code==403
        assert (await c.get('/python/simple/numpy/?send=private')).status_code==403
        assert (await c.post('/npm/react',content='private')).status_code==403
        assert (await c.request('CONNECT','/registry.npmjs.org:443')).status_code==403

@pytest.mark.asyncio
async def test_npm_tarballs_are_rewritten_and_immutable_hashes_checked(gateway,monkeypatch):
    m=gateway;old=(datetime.now(timezone.utc)-timedelta(days=10)).isoformat()
    async def metadata(url):return {'name':'react','versions':{'1.0.0':{'dist':{'tarball':'https://registry.npmjs.org/react/-/react.tgz','shasum':'0'*40},'dependencies':{'scheduler':'*'}},'2.0.0':{'dist':{'tarball':'https://registry.npmjs.org/new.tgz','shasum':'1'*40}}},'time':{'1.0.0':old,'2.0.0':datetime.now(timezone.utc).isoformat()},'dist-tags':{'latest':'2.0.0'}}
    async def fetch(*args,**kw):return b'wrong-content'
    monkeypatch.setattr(m,'metadata',metadata)
    monkeypatch.setattr(m,'upstream_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b'wrong-content'))))
    data=await m.npm_data('react')
    assert list(data['versions'])==['1.0.0'] and data['dist-tags']=={'latest':'1.0.0'}
    url=data['versions']['1.0.0']['dist']['tarball'];assert url.startswith(m.BASE)
    assert 'scheduler' in m.admitted['npm']
    with pytest.raises(m.HTTPException) as error:await m.artifact(url.rsplit('/',1)[-1])
    assert error.value.status_code==502

def test_override_is_exact_expiring_and_go_uses_first_observation(gateway):
    m=gateway;observed=m.first_observed('go','example.com/module','v1.0.0')
    assert not m.old_enough('go','example.com/module','v1.0.0',observed)
    p=m.policy();p['overrides']=[{'ecosystem':'go','package':'example.com/module','version':'v1.0.0','expires':time.time()+30}];m.POLICY.write_text(json.dumps(p))
    assert m.old_enough('go','example.com/module','v1.0.0',observed)
    assert not m.old_enough('go','example.com/module','v2.0.0',observed)
    p['overrides'][0]['expires']=time.time()-1;m.POLICY.write_text(json.dumps(p))
    assert not m.old_enough('go','example.com/module','v1.0.0',observed)

@pytest.mark.asyncio
async def test_unknown_upstream_is_never_fetched(gateway):
    for url in ['http://pypi.org/file','https://example.com/file','https://127.0.0.1/file','https://user:'+'password@pypi.org/file']:
        with pytest.raises(gateway.HTTPException) as error:await gateway.fetch(url)
        assert error.value.status_code==403

@pytest.mark.asyncio
async def test_nuget_uses_catalog_hash_not_unavailable_sha512_endpoint(gateway,monkeypatch):
    m=gateway;old=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    async def versions(name):return {'1.0.0':{'@id':'https://api.nuget.org/v3/catalog0/data/date/newtonsoft.json.1.0.0.json','published':old}}
    async def metadata(url):assert '/catalog0/data/' in url;return {'packageHash':'verified-hash','packageHashAlgorithm':'SHA512'}
    async def artifact(ident):return m.downloads[ident]
    monkeypatch.setattr(m,'nuget_versions',versions);monkeypatch.setattr(m,'metadata',metadata);monkeypatch.setattr(m,'artifact',artifact)
    entry=await m.nuget_package('newtonsoft.json','1.0.0','newtonsoft.json.1.0.0.nupkg')
    assert entry['digest']=='verified-hash' and entry['algorithm']=='sha512'

@pytest.mark.asyncio
async def test_julia_keeps_aged_snapshot_and_returns_server_relative_path(gateway,monkeypatch):
    m=gateway;name='registry/23338594-aafe-5451-b93e-139f81909106';oldhash='a'*40;newhash='b'*40
    old=(datetime.now(timezone.utc)-timedelta(days=6)).isoformat();m.CACHE.mkdir(exist_ok=True)
    (m.CACHE/'julia-first-seen.json').write_text(json.dumps({name+'@'+oldhash:old}))
    async def fetch(*args):return ('/'+name+'/'+newhash).encode()
    monkeypatch.setattr(m,'fetch',fetch)
    response=await m.julia('registries')
    assert response.body.decode()=='/'+name+'/'+oldhash
    assert not m.old_enough('julia',name,newhash,m.first_observed('julia',name,newhash))

def test_artifact_catalog_survives_process_restart(gateway):
    m=gateway;old=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    m.admit('npm',['dependency']);url=m.register('https://registry.npmjs.org/dependency/-/dependency.tgz','a'*64,'npm','dependency','1.0.0',old)
    m.save_catalog()
    spec=importlib.util.spec_from_file_location('package_gateway_restarted',Path(m.__file__));restarted=importlib.util.module_from_spec(spec);spec.loader.exec_module(restarted)
    assert url.rsplit('/',1)[-1] in restarted.downloads and 'dependency' in restarted.admitted['npm']

def test_large_wheel_catalog_does_not_block_unrelated_packages(gateway):
    m=gateway;old=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    entry=json.dumps({'url':'https://files.pythonhosted.org/fixture.whl','digest':'a'*64,'eco':'python','name':'many-wheels','version':'1','published':old})
    m.downloads.db.executemany('INSERT INTO artifacts VALUES (?,?)',((f'{i:064x}',entry) for i in range(20005)))
    url=m.register('https://registry.npmjs.org/react/-/react.tgz','b'*40,'npm','react','1.0.0',old,'sha1')
    revision=m.catalog_revision
    assert m.register('https://registry.npmjs.org/react/-/react.tgz','b'*40,'npm','react','1.0.0',old,'sha1')==url
    assert m.catalog_revision==revision
    m.save_catalog()
    assert m.downloads[url.rsplit('/',1)[-1]]['name']=='react'
    assert len(m.downloads)==20006

@pytest.mark.asyncio
async def test_large_npm_metadata_not_cached_and_other_hosts_keep_limit(gateway,monkeypatch):
    m=gateway;calls=[]
    async def fetch(url,maximum):
        calls.append((url,maximum));return json.dumps({'padding':'x'*1_000_001}).encode()
    monkeypatch.setattr(m,'fetch',fetch)
    npm='https://registry.npmjs.org/vite'
    await m.metadata(npm);await m.metadata(npm)
    assert calls==[(npm,64_000_000)]*2 and npm not in m.memo
    await m.metadata('https://pypi.org/pypi/numpy/json')
    assert calls[-1][1]==16_000_000

# Artifact tests exercise real streaming/hash verification with a synthetic registry.
import asyncio,hashlib

def add_artifact(m,name,payload,digest=None):
    old=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    return m.register('https://files.pythonhosted.org/'+name,hashlib.sha256(payload).hexdigest() if digest is None else digest,'python',name,'1',old).rsplit('/',1)[-1]

async def serve_response(response,fail=False):
    chunks=[]
    async def receive():return {'type':'http.disconnect'}
    async def send(message):
        assert message['type']!='http.response.pathsend'
        if message['type']=='http.response.body':
            if fail:raise asyncio.CancelledError()
            chunks.append(message.get('body',b''))
    await response({'type':'http','method':'GET','headers':[], 'extensions':{'http.response.pathsend':{}}},receive,send)
    return b''.join(chunks)

@pytest.mark.asyncio
async def test_concurrent_downloads_deduplicate_and_stream(gateway,monkeypatch):
    m=gateway;payload=b'package-data'*100000;ident=add_artifact(m,'large',payload);requests=[]
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for offset in range(0,len(payload),17000):
                yield payload[offset:offset+17000]
                await asyncio.sleep(0)
    async def registry(req):requests.append(req);return httpx.Response(200,stream=Stream())
    monkeypatch.setattr(m,'upstream_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(registry)))
    first,second=await asyncio.gather(m.artifact(ident),m.artifact(ident))
    assert len(requests)==1 and m.pins[ident]==2 and not m.artifact_locks
    assert await serve_response(first)==payload
    assert await serve_response(second)==payload
    assert not m.pins and m.reserved_bytes==0 and not list(m.CACHE.glob('.download-*'))

@pytest.mark.asyncio
async def test_active_responses_are_not_evicted_and_capacity_is_bounded(gateway,monkeypatch):
    m=gateway;monkeypatch.setattr(m,'MAX_BYTES',8);monkeypatch.setattr(m,'CACHE_BYTES',16)
    monkeypatch.setattr(m,'upstream_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b'12345678'))))
    a,b,c=[add_artifact(m,name,b'12345678') for name in ['first','second','third']]
    ra=await m.artifact(a);rb=await m.artifact(b)
    with pytest.raises(m.HTTPException) as error:await m.artifact(c)
    assert error.value.status_code==503 and m.reserved_bytes==0
    assert (m.CACHE/a).exists() and (m.CACHE/b).exists()
    await serve_response(ra)
    rc=await m.artifact(c)
    assert not (m.CACHE/a).exists() and (m.CACHE/b).exists()
    assert await serve_response(rb)==b'12345678'
    with pytest.raises(asyncio.CancelledError):await serve_response(rc,fail=True)
    assert not m.pins

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['checksum','oversized','interrupted'])
async def test_failed_download_never_publishes_partial_file(gateway,monkeypatch,failure):
    m=gateway;ident=add_artifact(m,'broken',b'expected')
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'partial'
            if failure=='interrupted':raise httpx.ReadError('connection lost')
    if failure=='oversized':monkeypatch.setattr(m,'MAX_BYTES',3)
    monkeypatch.setattr(m,'upstream_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,stream=Stream()))))
    with pytest.raises(m.HTTPException):await m.artifact(ident)
    assert not (m.CACHE/ident).exists() and not list(m.CACHE.glob('.download-*'))
    assert not m.pins and m.reserved_bytes==0 and not m.artifact_locks

@pytest.mark.asyncio
async def test_download_cancellation_releases_reservation(gateway,monkeypatch):
    m=gateway;started=asyncio.Event();ident=add_artifact(m,'cancel',b'expected')
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.sleep(60)
            yield b'expected'
    monkeypatch.setattr(m,'upstream_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,stream=Stream()))))
    task=asyncio.create_task(m.artifact(ident));await started.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert m.reserved_bytes==0 and not m.artifact_locks and not list(m.CACHE.glob('.download-*'))

@pytest.mark.asyncio
async def test_distinct_artifacts_download_in_parallel(gateway,monkeypatch):
    m=gateway;both_started=asyncio.Event();started=0
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal started
            started+=1
            if started==2:both_started.set()
            await asyncio.wait_for(both_started.wait(),2)
            yield b'content'
    monkeypatch.setattr(m,'upstream_client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,stream=Stream()))))
    responses=await asyncio.gather(*(m.artifact(add_artifact(m,n,b'content')) for n in ['one','two']))
    for response in responses:assert await serve_response(response)==b'content'
