"""Read-only, age-gated package facade. No arbitrary URL, CONNECT, publish or upload API."""
import asyncio,base64,hashlib,html,json,os,re,time,sqlite3,tempfile
from contextlib import asynccontextmanager
import anyio
from collections.abc import MutableMapping
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote,urlsplit
import httpx
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import Response,FileResponse
@asynccontextmanager
async def lifespan(app):
    # This service uses Recreate: no other replica can own these partial downloads.
    for partial in CACHE.glob('.download-*'):
        if partial.is_file():partial.unlink()
    yield

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
BASE='http://package-proxy.lab-control.svc.cluster.local:3128'
CACHE=Path(os.getenv('PACKAGE_CACHE','/cache'));POLICY=Path(os.getenv('PACKAGE_POLICY','/policy/packages.json'))
MAX_BYTES=250_000_000  # Approved limit for large coding-harness artifacts.
class ArtifactCatalog(MutableMapping):
    """Disk-backed registry: wheel metadata must not exhaust a global dict limit."""
    def __init__(self,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=10,check_same_thread=False)
        self.db.execute('PRAGMA max_page_count=65536')  # 256 MiB at default page size
        self.db.execute('CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, entry TEXT NOT NULL)')
        self.db.commit()
    def __getitem__(self,key):
        row=self.db.execute('SELECT entry FROM artifacts WHERE id=?',(key,)).fetchone()
        if row is None:raise KeyError(key)
        return json.loads(row[0])
    def __setitem__(self,key,value):
        try:self.db.execute('INSERT OR REPLACE INTO artifacts VALUES (?,?)',(key,json.dumps(value)))
        except sqlite3.Error:raise HTTPException(503,'Package catalog storage unavailable') from None
    def __delitem__(self,key):
        if not self.db.execute('DELETE FROM artifacts WHERE id=?',(key,)).rowcount:raise KeyError(key)
    def __iter__(self):return (r[0] for r in self.db.execute('SELECT id FROM artifacts'))
    def __len__(self):return self.db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]
    def commit(self):self.db.commit()

memo={}; admitted={}; downloads=ArtifactCatalog(CACHE/'artifacts.sqlite')
catalog_path=CACHE/'catalog.json'
if catalog_path.exists():
    saved=json.loads(catalog_path.read_text());downloads.update(saved.get('downloads',{}));downloads.commit();admitted.update({k:set(v) for k,v in saved.get('admitted',{}).items()})
catalog_revision=0;catalog_saved=0
def save_catalog():
    global catalog_saved
    downloads.commit()
    if catalog_revision==catalog_saved:return
    CACHE.mkdir(parents=True,exist_ok=True);temp=CACHE/'catalog.tmp'
    temp.write_text(json.dumps({'download_backend':'sqlite','admitted':{k:sorted(v) for k,v in admitted.items()}}));temp.replace(catalog_path);catalog_saved=catalog_revision
HOSTS={'pypi.org','files.pythonhosted.org','registry.npmjs.org','index.crates.io','crates.io','static.crates.io','proxy.golang.org','api.nuget.org','sum.golang.org','us-east.pkg.julialang.org','storage.julialang.net'}
def policy():return json.loads(POLICY.read_text())
def allowed(eco,name):
    # No package-name allowlist. Only fixed registry routes and valid identifiers.
    patterns={'python':r'[a-z0-9_.-]{1,120}','npm':r'(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]{1,160}',
              'cargo':r'[a-zA-Z0-9_-]{1,100}','nuget':r'[a-z0-9_.-]{1,120}',
              'go':r'[a-zA-Z0-9!._~/-]{1,240}','julia':r'(?:registry|package)/[a-f0-9-]{36}|artifact'}
    if eco not in patterns or not re.fullmatch(patterns[eco],name) or '..' in name or name.startswith('/'):
        raise HTTPException(400,'Invalid registry package identifier')
def admit(eco,names):
    global catalog_revision
    values=admitted.setdefault(eco,set())
    if len(values)>4000:raise HTTPException(503,'Package dependency catalog is full')
    before=len(values);values.update(names)
    if len(values)!=before:catalog_revision+=1
def old_enough(eco,name,version,published):
    p=policy()
    for entry in p.get('overrides',[]):
        if (entry.get('ecosystem'),entry.get('package'),entry.get('version'))==(eco,name,version) and entry.get('expires',0)>time.time():return True
    try:return datetime.fromisoformat(published.replace('Z','+00:00')).timestamp()<=time.time()-p.get('minimum_age_days',5)*86400
    except (AttributeError,ValueError,TypeError):return False
def upstream_client():
    return httpx.AsyncClient(timeout=45,proxy=os.getenv('UPSTREAM_PROXY') or None,follow_redirects=False,trust_env=False)

def validate_upstream(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password:raise HTTPException(403,'Upstream is not a package host')
async def fetch(url,maximum=16_000_000):
    validate_upstream(url)
    async with upstream_client() as client:
        async with client.stream('GET',url,headers={'User-Agent':'SandboxLab-package-gateway/1.0'}) as r:
            if r.status_code!=200:raise HTTPException(502,'Package registry could not supply this resource')
            data=bytearray()
            async for part in r.aiter_bytes():
                data.extend(part)
                if len(data)>maximum:raise HTTPException(413,'Package resource exceeds the lab size limit')
    return bytes(data)
async def metadata(url):
    value=memo.get(url)
    if value and value[0]>time.time():return value[1]
    # Full npm packuments include release timestamps needed by the age policy.
    # Large established packages exceed 16 MB; do not retain these in RAM.
    raw=await fetch(url,64_000_000 if urlsplit(url).hostname=='registry.npmjs.org' else 16_000_000)
    data=json.loads(raw)
    if len(raw)<=1_000_000:
        if len(memo)>=32:memo.pop(next(iter(memo)))
        memo[url]=(time.time()+300,data)
    return data
def register(url,digest,eco,name,version,published,algorithm='sha256'):
    global catalog_revision
    ident=hashlib.sha256((url+'|'+digest).encode()).hexdigest()
    entry={'url':url,'digest':digest,'algorithm':algorithm,'eco':eco,'name':name,'version':version,'published':published}
    if downloads.get(ident)!=entry:
        downloads[ident]=entry;catalog_revision+=1
    return BASE+'/artifact/'+ident
@app.middleware('http')
async def readonly(request,call_next):
    if request.method not in ['GET','HEAD'] or request.url.query or request.headers.get('authorization') or request.headers.get('cookie'):
        return Response('Only approved package reads are permitted',status_code=403)
    response=await call_next(request);save_catalog();response.headers['X-Content-Type-Options']='nosniff';return response
@app.get('/healthz')
async def health():return {'ready':True,'minimum_age_days':policy().get('minimum_age_days',5)}
# Bound disk reservations as well as RAM; concurrent downloads never exceed the cache budget.
CACHE_BYTES=700_000_000
artifact_locks={}
pins={}
reserved_bytes=0
cache_lock=asyncio.Lock()
download_slots=asyncio.Semaphore(2)

@asynccontextmanager
async def artifact_lock(ident):
    record=artifact_locks.setdefault(ident,[asyncio.Lock(),0])
    record[1]+=1
    try:
        async with record[0]:yield
    finally:
        record[1]-=1
        if not record[1]:artifact_locks.pop(ident,None)


def reserve_space(amount):
    global reserved_bytes
    files=sorted((p for p in CACHE.iterdir() if p.is_file() and re.fullmatch('[a-f0-9]{64}',p.name)),key=lambda p:p.stat().st_mtime)
    size=sum(p.stat().st_size for p in files)
    for old in files:
        if size+reserved_bytes+amount<=CACHE_BYTES:break
        if pins.get(old.name,0):continue
        size-=old.stat().st_size;old.unlink()
    if size+reserved_bytes+amount>CACHE_BYTES:
        raise HTTPException(503,'Package cache is busy serving downloads. Retry shortly.',headers={'Retry-After':'5'})
    reserved_bytes+=amount


def release_pin(ident):
    if pins.get(ident,0)<=1:pins.pop(ident,None)
    else:pins[ident]-=1


class PinnedFileResponse(FileResponse):
    def __init__(self,path,ident):
        super().__init__(path,media_type='application/octet-stream')
        self.ident=ident

    async def __call__(self,scope,receive,send):
        try:
            # Completion means bytes have been read, not merely a sendfile path handed off.
            scope={**scope,'extensions':{k:v for k,v in scope.get('extensions',{}).items() if k!='http.response.pathsend'}}
            await super().__call__(scope,receive,send)
        finally:
            release_pin(self.ident)


async def download_artifact(entry,destination):
    validate_upstream(entry['url'])
    digest=hashlib.new(entry['algorithm']);size=0
    try:
        async with upstream_client() as client:
            async with client.stream('GET',entry['url'],headers={'User-Agent':'SandboxLab-package-gateway/1.0'}) as response:
                if response.status_code!=200:raise HTTPException(502,'Package registry could not supply this resource')
                async with await anyio.open_file(destination,'wb') as output:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        size+=len(chunk)
                        if size>MAX_BYTES:raise HTTPException(413,'Package resource exceeds the lab size limit')
                        digest.update(chunk)
                        await output.write(chunk)
                    await output.flush()
        expected=entry['digest'];actual=digest.digest()
        if expected and actual.hex()!=expected and base64.b64encode(actual).decode()!=expected:
            raise HTTPException(502,'Package checksum mismatch')
    except httpx.HTTPError:
        raise HTTPException(502,'Package download interrupted; retry the package installation.') from None


@app.get('/artifact/{ident}')
async def artifact(ident):
    global reserved_bytes
    entry=downloads.get(ident)
    if not entry:raise HTTPException(404,'Resolve the package metadata again before downloading')
    allowed(entry['eco'],entry['name'])
    async with artifact_lock(ident):
        if not old_enough(entry['eco'],entry['name'],entry['version'],entry['published']):raise HTTPException(403,'Package release is younger than the minimum age')
        CACHE.mkdir(parents=True,exist_ok=True);path=CACHE/ident
        async with cache_lock:
            if path.exists():
                pins[ident]=pins.get(ident,0)+1;path.touch()
                return PinnedFileResponse(path,ident)
        async with download_slots:
            temporary=None;reserved=False
            try:
                async with cache_lock:
                    reserve_space(MAX_BYTES);reserved=True
                fd,name=tempfile.mkstemp(prefix='.download-',dir=CACHE);os.close(fd);temporary=Path(name)
                await download_artifact(entry,temporary)
                async with cache_lock:
                    temporary.replace(path)  # Only complete, verified files become visible.
                    reserved_bytes-=MAX_BYTES;reserved=False
                    pins[ident]=pins.get(ident,0)+1
                return PinnedFileResponse(path,ident)
            except OSError:
                raise HTTPException(503,'Package cache storage is unavailable; retry after capacity is restored.') from None
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
                if reserved:reserved_bytes-=MAX_BYTES

@app.get('/python/simple/{name}/')
async def python_simple(name):
    if not re.fullmatch('[A-Za-z0-9_.-]{1,120}',name):raise HTTPException(400)
    name=re.sub('[-_.]+','-',name).lower();allowed('python',name)
    data=await metadata('https://pypi.org/pypi/'+name+'/json');links=[]
    # Dependencies are catalogued for diagnostics, not used as an access allowlist.
    deps=[re.match(r'[A-Za-z0-9_.-]+',s).group(0) for s in data.get('info',{}).get('requires_dist') or [] if re.match(r'[A-Za-z0-9_.-]+',s)]
    admit('python',[re.sub('[-_.]+','-',s).lower() for s in deps])
    for version,files in data.get('releases',{}).items():
        for f in files:
            published=f.get('upload_time_iso_8601')
            if f.get('yanked') or not old_enough('python',name,version,published):continue
            if urlsplit(f['url']).hostname!='files.pythonhosted.org':continue
            digest=f.get('digests',{}).get('sha256')
            if not digest:continue
            url=register(f['url'],digest,'python',name,version,published)+'/'+quote(f['filename'])
            links.append('<a href="'+html.escape(url)+'#sha256='+digest+'" data-upload-time="'+html.escape(published)+'" data-requires-python="'+html.escape(f.get('requires_python') or '')+'">'+html.escape(f['filename'])+'</a>')
    return Response('<!doctype html><html><body>'+'\n'.join(links)+'</body></html>',media_type='text/html')
@app.get('/artifact/{ident}/{filename}')
async def named_artifact(ident,filename):return await artifact(ident)
async def npm_data(name):
    if not re.fullmatch(r'(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]{1,160}',name):raise HTTPException(400)
    allowed('npm',name);data=await metadata('https://registry.npmjs.org/'+quote(name,safe='@'))
    result={k:v for k,v in data.items() if k not in ['versions','dist-tags','time','readme','users']};versions={}
    for version,original in data.get('versions',{}).items():
        published=data.get('time',{}).get(version)
        if not old_enough('npm',name,version,published):continue
        item=json.loads(json.dumps(original));dist=item.get('dist',{});url=dist.get('tarball','')
        if urlsplit(url).hostname!='registry.npmjs.org':continue
        integrity=dist.get('integrity','');algorithm='sha256';digest=''
        if integrity.startswith('sha512-'):algorithm='sha512';digest=integrity.split('sha512-',1)[1].split()[0]
        elif dist.get('shasum'):algorithm='sha1';digest=dist['shasum']
        if not digest:continue
        dist['tarball']=register(url,digest,'npm',name,version,published,algorithm)
        versions[version]=item
        admit('npm',set(item.get('dependencies',{}))|set(item.get('optionalDependencies',{}))|set(item.get('peerDependencies',{})))
    result['versions']=versions;result['dist-tags']={k:v for k,v in data.get('dist-tags',{}).items() if v in versions}
    # npm install <name> should select the newest eligible stable release.
    if 'latest' not in result['dist-tags']:
        stable=[v for v in versions if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',v)]
        if stable:result['dist-tags']['latest']=max(stable,key=lambda v:tuple(int(x) for x in v.split('.')))
    result['time']={v:data['time'][v] for v in versions};return result
@app.get('/npm/{name:path}')
async def npm(name):return await npm_data(name)

async def crate_versions(name):
    allowed('cargo',name);data=await metadata('https://crates.io/api/v1/crates/'+quote(name))
    return {v['num']:v for v in data.get('versions',[]) if not v.get('yanked') and old_enough('cargo',name,v['num'],v.get('created_at'))}
@app.get('/cargo/index/config.json')
async def cargo_config():return {'dl':BASE+'/cargo/crates','api':BASE+'/disabled'}
@app.get('/cargo/index/{path:path}')
async def cargo_index(path):
    name=path.rsplit('/',1)[-1]
    if not re.fullmatch('[a-zA-Z0-9_-]{1,100}',name):raise HTTPException(400)
    versions=await crate_versions(name)
    canonical=(('1/'+name) if len(name)==1 else ('2/'+name) if len(name)==2 else ('3/'+name[0]+'/'+name) if len(name)==3 else name[:2]+'/'+name[2:4]+'/'+name)
    if path!=canonical:raise HTTPException(400)
    raw=await fetch('https://index.crates.io/'+path);result=[]
    for line in raw.decode().splitlines():
        item=json.loads(line)
        if item['vers'] in versions:
            result.append(line);admit('cargo',[d.get('package') or d['name'] for d in item.get('deps',[])])
    return Response('\n'.join(result)+'\n',media_type='text/plain')
@app.get('/cargo/crates/{name}/{version}/download')
async def crate_download(name,version):
    versions=await crate_versions(name);item=versions.get(version)
    if not item:raise HTTPException(403,'Crate is too recent or not approved')
    url=register('https://static.crates.io/crates/'+name+'/'+name+'-'+version+'.crate',item['checksum'],'cargo',name,version,item['created_at'])
    return await artifact(url.rsplit('/',1)[-1])

async def nuget_versions(name):
    if not re.fullmatch('[a-z0-9_.-]{1,120}',name):raise HTTPException(400)
    allowed('nuget',name);data=await metadata('https://api.nuget.org/v3/registration5-gz-semver2/'+name+'/index.json');items=[]
    for page in data.get('items',[]):
        if 'items' not in page:
            url=page.get('@id','')
            if not url.startswith('https://api.nuget.org/v3/registration5-gz-semver2/'+name+'/'):continue
            page=await metadata(url)
        for leaf in page.get('items',[]):
            item=leaf.get('catalogEntry',{})
            if isinstance(item,dict) and item.get('listed',True) and old_enough('nuget',name,item.get('version','').lower(),item.get('published')):items.append(item)
    for item in items:
        admit('nuget',[d['id'].lower() for g in item.get('dependencyGroups',[]) for d in g.get('dependencies',[])])
    return {i['version'].lower():i for i in items}
@app.get('/nuget/v3/index.json')
async def nuget_index():
    return {'version':'3.0.0','resources':[{'@id':BASE+'/nuget/flat/','@type':'PackageBaseAddress/3.0.0'},{'@id':BASE+'/nuget/registration/','@type':'RegistrationsBaseUrl/3.6.0'}]}
@app.get('/nuget/flat/{name}/index.json')
async def nuget_list(name):return {'versions':list(await nuget_versions(name))}
@app.get('/nuget/registration/{name}/index.json')
async def nuget_registration(name):
    items=await nuget_versions(name);leaves=[{'catalogEntry':item,'packageContent':BASE+f'/nuget/flat/{name}/{v}/{name}.{v}.nupkg'} for v,item in items.items()]
    return {'count':1,'items':[{'count':len(leaves),'items':leaves}]}
@app.get('/nuget/flat/{name}/{version}/{filename}')
async def nuget_package(name,version,filename):
    item=(await nuget_versions(name)).get(version)
    if not item or filename!=f'{name}.{version}.nupkg':raise HTTPException(403,'Package version is too recent or not approved')
    url=f'https://api.nuget.org/v3-flatcontainer/{name}/{version}/{filename}'
    catalog_url=item.get('@id','')
    if not catalog_url.startswith('https://api.nuget.org/v3/catalog0/data/') or not catalog_url.endswith('/'+name+'.'+version+'.json'):raise HTTPException(502,'Missing authoritative NuGet catalog entry')
    catalog=await metadata(catalog_url)
    digest=catalog.get('packageHash','')
    if catalog.get('packageHashAlgorithm','').upper()!='SHA512' or not digest:raise HTTPException(502,'Missing NuGet package checksum')
    ref=register(url,digest,'nuget',name,version,item['published'],'sha512')
    return await artifact(ref.rsplit('/',1)[-1])

def first_observed(ecosystem,name,version):
    # Go .info.Time is a commit timestamp, not proof of publication age.
    # Quarantine from our first observation instead of trusting backdated commits.
    CACHE.mkdir(parents=True,exist_ok=True);path=CACHE/(ecosystem+'-first-seen.json')
    state=json.loads(path.read_text()) if path.exists() else {}
    key=name+'@'+version
    if key not in state:
        if len(state)>=5000:raise HTTPException(503,'Quarantine catalog is full; ask the operator to review it')
        state[key]=datetime.now(timezone.utc).isoformat();path.write_text(json.dumps(state))
    return state[key]
@app.get('/go/{module:path}/@v/{filename}')
async def go_resource(module,filename):
    if not re.fullmatch('[a-zA-Z0-9!._~/-]{1,240}',module) or '..' in module:raise HTTPException(400)
    allowed('go',module)
    prefix='https://proxy.golang.org/'+module+'/@v/'
    if filename=='list':
        raw=(await fetch(prefix+'list',1_000_000)).decode().splitlines()
        return Response('\n'.join(v for v in raw if old_enough('go',module,v,first_observed('go',module,v))),media_type='text/plain')
    match=re.fullmatch(r'(v[0-9A-Za-z.+_-]{1,100})\.(info|mod|zip)',filename)
    if not match:raise HTTPException(400)
    version,kind=match.groups();published=first_observed('go',module,version)
    if not old_enough('go',module,version,published):raise HTTPException(403,'Go version is quarantined for five days from first observation; an explicit version override can release it')
    if kind=='zip':
        ref=register(prefix+filename,'','go',module,version,published)
        return await artifact(ref.rsplit('/',1)[-1])
    raw=await fetch(prefix+filename,1_000_000)
    if kind=='mod':
        names=re.findall(r'^\s*(?:require\s+)?([a-zA-Z0-9!._~/-]+)\s+v[0-9]',raw.decode(),re.M);admit('go',names)
    return Response(raw,media_type='application/json' if kind=='info' else 'text/plain')
@app.get('/go/sumdb/sum.golang.org/{path:path}')
async def go_sumdb(path):
    if path=='supported':return Response('')
    if path.startswith('lookup/'):
        name,sep,version=path.removeprefix('lookup/').rpartition('@');allowed('go',name)
        if not sep or not re.fullmatch('v[0-9A-Za-z.+_-]{1,100}',version):raise HTTPException(400)
        if not old_enough('go',name,version,first_observed('go',name,version)):raise HTTPException(403,'Go checksum lookup is quarantined with its module version')
    elif not re.fullmatch(r'tile/[0-9/px.]{1,100}',path):raise HTTPException(403)
    return Response(await fetch('https://sum.golang.org/'+path,2_000_000),media_type='text/plain')
@app.get('/julia/{path:path}')
async def julia(path):
    if path=='registries':
        # Stable conservative-registry discovery is the only upstream list request.
        raw=(await fetch('https://us-east.pkg.julialang.org/registries.conservative',50000)).decode()
        registry=[]
        for line in raw.splitlines():
            if re.fullmatch(r'/registry/[a-f0-9-]{36}/[a-f0-9]{40}',line):
                name,version=line.lstrip('/').rsplit('/',1);admit('julia',[name])
                first_observed('julia',name,version)
        # Retain aged snapshots even when today's upstream registry hash changes.
        known=json.loads((CACHE/'julia-first-seen.json').read_text())
        selected={}
        for key,published in sorted(known.items(),key=lambda item:item[1]):
            name,version=key.rsplit('@',1)
            if name.startswith('registry/') and old_enough('julia',name,version,published):selected[name]=version
        registry=['/'+name+'/'+version for name,version in selected.items()]
        if not registry:raise HTTPException(403,'Julia registry snapshots are quarantined for five days from first observation; use a reviewed snapshot override to initialize sooner')
        return Response('\n'.join(registry),media_type='text/plain')
    if not re.fullmatch(r'(?:registry|package)/[a-f0-9-]{36}/[a-f0-9]{40}|artifact/[a-f0-9]{40,64}',path):raise HTTPException(403)
    name,version=path.rsplit('/',1)
    # Julia content identifiers are immutable; no arbitrary host/path is accepted.
    published=first_observed('julia',name,version)
    if not old_enough('julia',name,version,published):raise HTTPException(403,'Julia content is quarantined for five days from first observation')
    admit('julia',[name]);ref=register('https://storage.julialang.net/'+path,'','julia',name,version,published)
    return await artifact(ref.rsplit('/',1)[-1])
