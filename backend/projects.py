"""Human project browser and local-only OneDrive mock. No model or cloud sync calls."""
import asyncio,base64,json,os,re,shlex,shutil,tempfile,time,uuid
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from fastapi import HTTPException,Request
from chatkit.store import NotFoundError
from chatkit.types import ThreadMetadata
from .config import ROOT,STATE,CODER_URL


def safe_path(value):
    if not isinstance(value,str) or not value or len(value)>1024 or '\\' in value or '\x00' in value:raise ValueError('Invalid path')
    parts=value.split('/')
    if len(parts)>16 or any(p in ('','.', '..') for p in parts):raise ValueError('Invalid path')
    if any((p.startswith('.') and p!='.lab') or p in ('node_modules','venv','target','__pycache__') or p.lower().endswith(('.pem','.key','.p12','.pfx')) for p in parts):raise ValueError('Excluded path')
    return PurePosixPath(value)


def write_mock_sync(project_id,payload,root=None):
    if not re.fullmatch('prj_[a-f0-9]{32}',project_id):raise ValueError('Invalid project')
    root=root or STATE/'mock-onedrive'/'Projects'
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    files=payload.get('files')
    if not isinstance(files,list) or len(files)>2000:raise ValueError('Invalid export')
    base=root/project_id;base.mkdir(exist_ok=True,mode=0o700)
    stage=Path(tempfile.mkdtemp(prefix='.sync-',dir=base));previous=base/'previous';latest=base/'files'
    size=0;manifest=[];seen=set()
    try:
        for entry in files:
            path=safe_path(entry['path'])
            if str(path) in seen:raise ValueError('Duplicate export path')
            seen.add(str(path));raw=base64.b64decode(entry['data'],validate=True)
            size+=len(raw)
            if len(raw)>8_000_000 or size>32_000_000:raise ValueError('Export exceeds sync limits')
            dest=stage/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);dest.chmod(0o600)
            manifest.append({'path':str(path),'bytes':len(raw)})
        result={'mock':True,'synced_at':time.time(),'file_count':len(files),'bytes':size,'excluded':payload.get('excluded',0),'destination':'OneDrive (mock)/Projects/'+project_id,'files':manifest}
        (stage/'.sync-manifest.json').write_text(json.dumps(result));(stage/'.sync-manifest.json').chmod(0o600)
        # Retain only the latest mock mirror, with rollback if publication fails.
        if previous.exists():shutil.rmtree(previous)
        if latest.exists():latest.rename(previous)
        try:stage.rename(latest)
        except BaseException:
            if previous.exists():previous.rename(latest)
            raise
        if previous.exists():shutil.rmtree(previous)
        return {k:v for k,v in result.items() if k!='files'}
    finally:
        if stage.exists():shutil.rmtree(stage)


class ProjectFiles:
    def __init__(self,store,coder):self.store=store;self.coder=coder

    async def workspace(self,project,owner,wake=False):
        if wake:
            rows=self.store.db.execute('SELECT thread FROM project_threads WHERE project=? LIMIT 1',(project['id'],)).fetchall()
            if not rows:raise HTTPException(409,'Start a conversation in this project first.')
            thread=await self.store.load_thread(rows[0][0],{'owner':owner})
            ws=await self.coder.workspace(thread,self.store,{'owner':owner})
        else:
            if not project['workspace_id']:raise HTTPException(409,'Open the project to start its workspace.')
            ws=await self.coder.api('GET','/api/v2/workspaces/'+project['workspace_id'])
            if ws.get('deleted') or ws['latest_build']['status']!='running':raise HTTPException(409,'Workspace is sleeping. Open workspace files to resume.')
        if ws['template_id']!=self.coder.settings()['template_id']:raise HTTPException(403,'Headless template mismatch')
        self.coder.touched[ws['id']]=time.time()
        return ws

    async def read(self,workspace,action,path='',developer=None):
        if path:safe_path(path)
        result=await self.invoke(workspace,(ROOT/'sandbox/project_files.py').read_text(),{'action':action,'path':path},developer)
        if action=='list':
            entries=result.get('entries',[])
            if len(entries)>2000:raise ValueError('Too many entries')
            for entry in entries:safe_path(entry['path'])
        return result

    async def invoke(self,workspace,script,payload,developer=None):
        token=developer.token if developer else self.coder.settings()['token']
        env=dict(os.environ,CODER_URL='http://127.0.0.1:7080' if developer else CODER_URL,CODER_SESSION_TOKEN=token,CODER_CONFIG_DIR=str(STATE/('coder-dev-transfer-cli' if developer else 'coder-service-cli')),CODER_USE_KEYRING='false')
        proc=await asyncio.create_subprocess_exec(str(ROOT/'.local/bin/coder'),'ssh','--disable-autostart',workspace['name'],'--','python -I -c '+shlex.quote(script),env=env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        async def bounded(stream,maximum):
            data=bytearray()
            while part:=await stream.read(65536):
                data.extend(part)
                if len(data)>maximum:raise ValueError('Project response exceeded size limit')
            return data
        try:
            proc.stdin.write(json.dumps(payload).encode());await proc.stdin.drain();proc.stdin.close()
            out,_=await asyncio.wait_for(asyncio.gather(bounded(proc.stdout,48_000_000),bounded(proc.stderr,32000)),60)
            await proc.wait();result=json.loads(out)
            if proc.returncode or result.get('error'):raise ValueError('Project path unavailable or export exceeds limits. Dependencies, credential files and symlinks are excluded.')
            return result
        finally:
            if proc.returncode is None:proc.kill();await proc.wait()


def install_projects(app,store,coder,live_containers):
    from .project_actions import install_project_actions
    deletions=install_project_actions(app,store,coder)
    browser=ProjectFiles(store,coder)
    def owned(pid,request):
        try:
            project=store.get_project(pid,request.state.owner)
            if project['deleting']:raise HTTPException(409,'Project deletion is in progress')
            if project['archived']:raise HTTPException(409,'Restore this project before opening its workspace')
            return project
        except NotFoundError:raise HTTPException(404,'Project not found')

    @app.get('/api/projects')
    async def list_projects(request:Request):
        projects=store.projects(request.state.owner);live=await live_containers.get()
        operations={pid:{'status':status,'phase':phase,'error':error} for pid,status,phase,error in store.db.execute('SELECT id,status,phase,error FROM project_deletions WHERE owner=? AND status!=?',(request.state.owner,'deleted'))}
        pods={x['workspace_id']:x for x in live['pods'] if x['namespace']=='lab-agents' and x['workspace_id']}
        dev_pods={x['workspace_id']:x for x in live['pods'] if x['namespace']=='lab-dev' and x['workspace_id']}
        for p in projects:
            p['deletion']=operations.get(p['id'])
            pod=pods.get(p['workspace_id'])
            p['status']='delete failed' if p['deletion'] and p['deletion']['status']=='failed' else 'deleting' if p['deleting'] else 'unknown' if 'lab-agents' in live['unavailable_namespaces'] else pod['state'] if pod else 'stopped' if p['workspace_id'] else 'not started'
            p['developer_status']='unknown' if 'lab-dev' in live['unavailable_namespaces'] else dev_pods[p['developer_workspace_id']]['state'] if p['developer_workspace_id'] in dev_pods else 'stopped' if p['developer_workspace_id'] else None
        return projects

    @app.post('/api/projects/{pid}/threads')
    async def new_thread(pid:str,request:Request):
        owned(pid,request)
        thread=ThreadMetadata(id=store.generate_thread_id({}),title='New conversation',created_at=datetime.now(timezone.utc))
        await store.save_thread(thread,{'owner':request.state.owner});store.attach_project(thread,request.state.owner,pid)
        return {'id':thread.id,'project_id':pid}

    @app.post('/api/projects/{pid}/open')
    async def open_project(pid:str,request:Request):
        project=owned(pid,request)
        try:
            ws=await browser.workspace(project,request.state.owner,True)
            return await browser.read(ws,'list')
        except (ValueError,RuntimeError,asyncio.TimeoutError):raise HTTPException(503,'Could not open project files. Retry when the workspace is ready.')

    @app.get('/api/projects/{pid}/files')
    async def files(pid:str,request:Request,path:str=''):
        project=owned(pid,request)
        try:return await browser.read(await browser.workspace(project,request.state.owner),'list',path)
        except ValueError as exc:raise HTTPException(400,str(exc))
        except (RuntimeError,asyncio.TimeoutError):raise HTTPException(503,'Project file browser is temporarily unavailable.')

    @app.get('/api/projects/{pid}/file')
    async def file(pid:str,request:Request,path:str):
        project=owned(pid,request)
        try:return await browser.read(await browser.workspace(project,request.state.owner),'read',path)
        except ValueError as exc:raise HTTPException(400,str(exc))
        except (RuntimeError,asyncio.TimeoutError):raise HTTPException(503,'Project file is temporarily unavailable.')

    @app.post('/api/projects/{pid}/sync-onedrive')
    async def sync(pid:str,request:Request):
        project=owned(pid,request);lock=coder.project_locks.setdefault(pid,asyncio.Lock())
        if lock.locked():raise HTTPException(409,'This project is working. Sync after its coding run finishes.')
        async with lock:
            try:
                ws=await browser.workspace(project,request.state.owner,True)
                payload=await browser.read(ws,'export')
                result=await asyncio.to_thread(write_mock_sync,pid,payload)
                store.save_project_sync(pid,request.state.owner,result)
                return result
            except (ValueError,RuntimeError,asyncio.TimeoutError):raise HTTPException(400,'Mock sync could not complete. Previous copy retained. Limit: 2,000 files, 8 MB per file, 32 MB total.')

    return deletions
