"""Human-only project handoffs and reviewed return copies across separate workspaces."""
import asyncio,base64,hashlib,json,time,uuid
from fastapi import HTTPException,Request
from pydantic import BaseModel,ConfigDict
from typing import Literal
from chatkit.store import NotFoundError
from .config import ROOT,STATE
from .projects import ProjectFiles,safe_path
from .project_deletions import active_threads

class Link(BaseModel):
    model_config=ConfigDict(extra='forbid')
    project_id:str|None=None

class TransferRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    direction:Literal['to_chat','to_developer']

class TransferApproval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    plan_id:str

def checked_files(payload):
    entries=payload.get('files',[])
    if not isinstance(entries,list) or len(entries)>2000:raise ValueError('Too many files')
    files=[];seen=set();total=0
    for entry in entries:
        path=str(safe_path(entry['path']))
        if path in seen:raise ValueError('Duplicate path')
        raw=base64.b64decode(entry['data'],validate=True);total+=len(raw)
        if len(raw)>8_000_000 or total>32_000_000:raise ValueError('Files exceed sync limit')
        seen.add(path);files.append({'path':path,'data':entry['data'],'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    return files

class WorkspaceLinks:
    def __init__(self,store,coder,developer):
        self.store=store;self.coder=coder;self.developer=developer;self.browser=ProjectFiles(store,coder);self.plans={};self.preparing=0;self.slots=asyncio.Semaphore(2)

    def project(self,pid,owner):
        try:p=self.store.get_project(pid,owner)
        except NotFoundError:raise HTTPException(404,'Project not found')
        if p['archived'] or p['deleting']:raise HTTPException(409,'Restore the project or finish deletion first')
        return p

    def idle(self,p,owner):
        tids={r[0] for r in self.store.db.execute('SELECT thread FROM project_threads WHERE project=?',(p['id'],))}
        if active_threads(self.store,tids,owner) or p['workspace_id'] in self.coder.active or p['workspace_id'] in self.coder.provisioning:raise HTTPException(409,'Wait for this project’s coding run to finish before syncing')

    async def dev_workspace(self,wid,wake=False):
        ws=next((w for w in await self.developer.list() if w['id']==wid),None)
        if not ws:raise HTTPException(404,'Linked developer workstation no longer exists')
        if wake and ws['status'] in ('stopped','failed','canceled'):
            ws=await self.developer.start(ws['name'])
        if ws['status'] not in ('running','starting','pending'):raise HTTPException(409,'Wait for the developer workstation operation to finish')
        if wake:await self.developer.prepare(ws)
        self.developer.touched[wid]=time.time()
        return ws

    def expire(self):
        self.plans={key:p for key,p in self.plans.items() if p['expires']>time.monotonic()}

    async def open_developer(self,pid,owner):
        p=self.project(pid,owner)
        lock=self.coder.project_locks.setdefault(pid,asyncio.Lock())
        if lock.locked():raise HTTPException(409,'This project is busy; retry when its current operation finishes')
        async with lock:
            p=self.project(pid,owner)
            self.idle(p,owner)
            if p['developer_workspace_id']:
                ws=await self.dev_workspace(p['developer_workspace_id'],True)
            else:
                # Stable name makes retry after a lost response reuse the same workstation.
                ws=await self.developer.start('project-'+pid.removeprefix('prj_')[:20])
                p=self.store.link_developer(ws['id'],owner,ws['name'],pid)
                await self.developer.prepare(ws)
            result={**ws,'project_id':pid,'project_name':p['name']}
            if p['workspace_id']:
                async with self.slots:
                    ai=await self.browser.workspace(p,owner,True)
                    source=await self.browser.read(ai,'export')
                    files=checked_files(source)
                    if files:
                        # Same project + source snapshot opens the same developer copy.
                        # Local edits there are retained, never overwritten on reopen.
                        manifest=sorted((f['path'],f['sha256']) for f in files)
                        digest=hashlib.sha256(json.dumps([pid,manifest]).encode()).hexdigest()
                        key='transfer_'+digest[:32]
                        copied=await self.browser.invoke(ws,(ROOT/'sandbox/import_project.py').read_text(),{'id':key,'files':files,'reuse':True},self.developer)
                        copied.update(direction='to_developer',at=time.time(),developer_source_path=copied['path'])
                        with self.store.db:self.store.db.execute('UPDATE projects SET workspace_sync=? WHERE id=? AND owner=?',(json.dumps(copied),pid,owner))
                        result.update(source_path=copied['path'],source_copy=copied)
            return result

    async def plan(self,pid,owner,direction):
        p=self.project(pid,owner)
        if not p['developer_workspace_id']:raise HTTPException(409,'Link a developer workstation first')
        if not p['workspace_id']:raise HTTPException(409,'Ask a project chat to use its coding sandbox first. Linking does not allocate chat compute.')
        lock=self.coder.project_locks.setdefault(pid,asyncio.Lock())
        if lock.locked():raise HTTPException(409,'This project is busy')
        async with lock,self.slots:
            self.expire()
            if len(self.plans)+self.preparing>=2:raise HTTPException(429,'Close an earlier sync review or wait five minutes')
            self.preparing+=1
            try:
                self.idle(p,owner)
                dev=await self.dev_workspace(p['developer_workspace_id'],True)
                ai=await self.browser.workspace(p,owner,True)
                from_dev=direction=='to_chat'
                developer_path=(p.get('workspace_sync') or {}).get('developer_source_path','')
                source=await self.browser.read(dev if from_dev else ai,'export',path=developer_path if from_dev else '',developer=self.developer if from_dev else None)
                destination=await self.browser.read(ai if from_dev else dev,'export',path='' if from_dev else developer_path,developer=None if from_dev else self.developer)
                files=checked_files(source);existing={f['path']:f['sha256'] for f in checked_files(destination)}
                if not files:raise HTTPException(409,'No eligible source files to copy')
                key='transfer_'+uuid.uuid4().hex
                review=[{'path':f['path'],'bytes':f['bytes'],'change':'new' if f['path'] not in existing else 'unchanged' if f['sha256']==existing[f['path']] else 'different'} for f in files]
                self.plans[key]={'owner':owner,'project':pid,'direction':direction,'files':files,'workspace_id':p['workspace_id'],'developer_workspace_id':p['developer_workspace_id'],'expires':time.monotonic()+300}
                return {'id':key,'direction':direction,'files':review,'bytes':sum(f['bytes'] for f in files),'excluded':source.get('excluded',0),'path':'.lab/imports/'+key,'expires_in':300}
            finally:self.preparing-=1

    async def apply(self,pid,owner,key):
        self.expire();plan=self.plans.get(key)
        if not plan or plan['owner']!=owner or plan['project']!=pid:raise HTTPException(404,'Sync review expired or was not found')
        p=self.project(pid,owner);lock=self.coder.project_locks.setdefault(pid,asyncio.Lock())
        if lock.locked():raise HTTPException(409,'This project is busy')
        async with lock:
            self.idle(p,owner)
            if any(p[k]!=plan[k] for k in ('workspace_id','developer_workspace_id')):raise HTTPException(409,'Workspace links changed; review the sync again')
            to_dev=plan['direction']=='to_developer'
            ws=await self.dev_workspace(p['developer_workspace_id'],True) if to_dev else await self.browser.workspace(p,owner,True)
            result=await self.browser.invoke(ws,(ROOT/'sandbox/import_project.py').read_text(),{'id':key,'files':plan['files']},self.developer if to_dev else None)
            result.update(direction=plan['direction'],at=time.time())
            result['developer_source_path']=result['path'] if to_dev else (p.get('workspace_sync') or {}).get('developer_source_path','')
            with self.store.db:self.store.db.execute('UPDATE projects SET workspace_sync=? WHERE id=? AND owner=?',(json.dumps(result),pid,owner))
            self.plans.pop(key,None)
            return result

    async def maintain(self):
        while True:self.expire();await asyncio.sleep(30)

    async def migrate(self):
        marker=STATE/'developer-project-links-v1.done'
        if marker.exists():return
        try:
            for ws in await self.developer.list():self.store.link_developer(ws['id'],'local-owner',ws['name'])
            marker.write_text('complete')
        except Exception:pass  # A disconnected portal must not delay app startup; explicit linking stays available.

def install_workspace_links(app,store,coder,developer):
    links=WorkspaceLinks(store,coder,developer)
    @app.post('/api/projects/{pid}/developer-workspace')
    async def open_developer(pid:str,request:Request):
        try:return await links.open_developer(pid,request.state.owner)
        except RuntimeError as exc:raise HTTPException(503,str(exc))
        except (ValueError,asyncio.TimeoutError):raise HTTPException(503,'Could not copy source and open the workstation. Check readiness, source size, and the three-import limit.')

    @app.post('/api/developer/workspaces/{wid}/project')
    async def link(wid:str,request:Request,body:Link):
        ws=next((w for w in await developer.list() if w['id']==wid),None)
        if not ws:raise HTTPException(404,'Workspace not found')
        try:
            old=store.developer_project(wid,request.state.owner)
            for pid in {p for p in [body.project_id,old['id'] if old else None] if p}:
                p=links.project(pid,request.state.owner);links.idle(p,request.state.owner)
                if coder.project_locks.setdefault(pid,asyncio.Lock()).locked():raise HTTPException(409,'This project is busy')
            return store.link_developer(wid,request.state.owner,ws['name'],body.project_id)
        except NotFoundError:raise HTTPException(404,'Project not found')
        except ValueError as exc:raise HTTPException(409,str(exc))
    @app.post('/api/projects/{pid}/workspace-sync/plan')
    async def plan(pid:str,request:Request,body:TransferRequest):
        try:return await links.plan(pid,request.state.owner,body.direction)
        except (ValueError,RuntimeError,asyncio.TimeoutError):raise HTTPException(503,'Could not read both workspaces. Check that they are ready and the source fits the 2,000-file / 32 MB limits.')
    @app.post('/api/projects/{pid}/workspace-sync/apply')
    async def apply(pid:str,request:Request,body:TransferApproval):
        try:return await links.apply(pid,request.state.owner,body.plan_id)
        except (ValueError,RuntimeError,asyncio.TimeoutError):raise HTTPException(503,'Copy did not complete. Check that the destination is ready and has fewer than three imports; live source files were not replaced.')
    @app.delete('/api/projects/{pid}/workspace-sync/{key}')
    async def discard(pid:str,key:str,request:Request):
        p=links.plans.get(key)
        if p and p['project']==pid and p['owner']==request.state.owner:links.plans.pop(key,None)
        return {'discarded':True}
    return links
