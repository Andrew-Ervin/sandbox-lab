"""Automatic source handoffs when entering separate chat/GUI workspaces."""
from .limits import value
import asyncio,base64,hashlib,json,time
from fastapi import HTTPException,Request
from pydantic import BaseModel,ConfigDict
from datetime import datetime,timezone
from chatkit.types import ThreadMetadata
from chatkit.store import NotFoundError
from .config import ROOT,STATE
from .projects import ProjectFiles,safe_path
from .project_deletions import active_threads
from .source_sync import SourceSync
from typing import Literal

class ResolveConflict(BaseModel):
    model_config=ConfigDict(extra='forbid')
    path:str
    keep:Literal['chat','developer']

class Link(BaseModel):
    model_config=ConfigDict(extra='forbid')
    project_id:str|None=None

def checked_files(payload):
    entries=payload.get('files',[])
    if not isinstance(entries,list) or len(entries)>value('SYNC_MAX_FILES'):raise ValueError('Too many files')
    files=[];seen=set();total=0
    for entry in entries:
        path=str(safe_path(entry['path']))
        if path in seen:raise ValueError('Duplicate path')
        raw=base64.b64decode(entry['data'],validate=True);total+=len(raw)
        if len(raw)>value('SYNC_MAX_FILE_BYTES') or total>value('SYNC_MAX_TOTAL_BYTES'):raise ValueError('Files exceed sync limit')
        seen.add(path);files.append({'path':path,'data':entry['data'],'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    return files

class WorkspaceLinks:
    def __init__(self,store,coder,developer):
        self.store=store;self.coder=coder;self.developer=developer;self.browser=ProjectFiles(store,coder);self.slots=asyncio.Semaphore(value('SYNC_CONCURRENCY'));self.sync=SourceSync(self)

    def project(self,pid,owner):
        try:p=self.store.get_project(pid,owner)
        except NotFoundError:raise HTTPException(404,'Project not found')
        if p['archived'] or p['deleting']:raise HTTPException(409,'Restore the project or finish deletion first')
        return p

    def idle(self,p,owner,except_thread=None):
        tids={r[0] for r in self.store.db.execute('SELECT thread FROM project_threads WHERE project=?',(p['id'],))}
        if active_threads(self.store,tids-{except_thread},owner) or p['workspace_id'] in self.coder.active or p['workspace_id'] in getattr(self.coder,'native_active',set()) or p['workspace_id'] in self.coder.provisioning:raise HTTPException(409,'Wait for this project’s coding run to finish before syncing')

    async def dev_workspace(self,wid,wake=False):
        ws=next((w for w in await self.developer.list() if w['id']==wid),None)
        if not ws:raise HTTPException(404,'Linked developer workstation no longer exists')
        if wake and ws['status'] in ('stopped','failed','canceled'):
            ws=await self.developer.start(ws['name'])
        if ws['status'] not in ('running','starting','pending'):raise HTTPException(409,'Wait for the developer workstation operation to finish')
        if wake:await self.developer.prepare(ws)
        self.developer.touched[wid]=time.time()
        return ws

    @staticmethod
    def paths(p):
        sync=p.get('workspace_sync') or {}
        return (sync.get('chat_source_path',sync.get('path','') if sync.get('direction')=='to_chat' else ''),
                sync.get('developer_source_path',''))

    async def open_developer(self,pid,owner):
        p=self.project(pid,owner)
        lock=self.coder.project_locks.setdefault(pid,asyncio.Lock())
        if lock.locked() and pid not in self.sync.background:raise HTTPException(409,'This project is busy; retry when its current operation finishes')
        async with lock,self.slots:
            p=self.project(pid,owner);self.idle(p,owner)
            if p['developer_workspace_id']:
                ws=await self.dev_workspace(p['developer_workspace_id'],True)
            else:
                ws=await self.developer.start('project-'+pid.removeprefix('prj_')[:20])
                p=self.store.link_developer(ws['id'],owner,ws['name'],pid)
                await self.developer.prepare(ws)
            chat_path,dev_path=self.paths(p)
            result={**ws,'project_id':pid,'project_name':p['name'],'source_path':dev_path}
            if p['workspace_id']:
                ai=await self.browser.workspace(p,owner,True)
                synced=await self.sync.run(p,owner,ai,ws)
                result.update(source_path=dev_path,source_copy=synced)
            return result

    async def sync_chat(self,pid,owner,thread):
        p=self.project(pid,owner)
        lock=self.coder.project_locks.setdefault(pid,asyncio.Lock())
        if lock.locked() and pid not in self.sync.background:raise HTTPException(409,'This project is busy; retry when its current operation finishes')
        async with lock,self.slots:
            p=self.project(pid,owner);self.idle(p,owner,except_thread=thread.id)
            if p['developer_workspace_id']:
                dev=await self.dev_workspace(p['developer_workspace_id'],True)
                chat_path,dev_path=self.paths(p)
                snapshot=await self.browser.read(dev,'manifest',path=dev_path,developer=self.developer)
                if p['workspace_id'] or snapshot['files']:
                    ai=await self.browser.workspace(p,owner,True)
                    p=self.project(pid,owner)
                    await self.sync.run(p,owner,ai,dev)
            thread.metadata['workspace_entry_synced']=True
            self.store.apply_project_metadata(thread,owner)
            await self.store.save_thread(thread,{'owner':owner})

    async def start_chat(self,pid,owner):
        self.project(pid,owner)
        thread=ThreadMetadata(id=self.store.generate_thread_id({}),title='New conversation',created_at=datetime.now(timezone.utc))
        await self.store.save_thread(thread,{'owner':owner});self.store.attach_project(thread,owner,pid)
        try:await self.sync_chat(pid,owner,thread)
        except BaseException:
            # No message exists yet. A failed handoff should not leave duplicate
            # empty conversations when the user retries; project storage survives.
            with self.store.db:
                self.store.db.execute('DELETE FROM project_threads WHERE thread=?',(thread.id,))
                self.store.db.execute('DELETE FROM threads WHERE id=?',(thread.id,))
            raise
        return {'id':thread.id,'project_id':pid}

    async def resolve(self,pid,owner,path,keep):
        p=self.project(pid,owner);lock=self.coder.project_locks.setdefault(pid,asyncio.Lock())
        if lock.locked() and pid not in self.sync.background:raise HTTPException(409,'This project is busy')
        async with lock,self.slots:
            p=self.project(pid,owner);self.idle(p,owner)
            if not p['workspace_id'] or not p['developer_workspace_id']:raise HTTPException(409,'Both workspaces are required')
            ai=await self.browser.workspace(p,owner,True)
            dev=await self.dev_workspace(p['developer_workspace_id'],True)
            return await self.sync.run(p,owner,ai,dev,resolution=(str(safe_path(path)),keep))

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
        except (ValueError,asyncio.TimeoutError):raise HTTPException(503,'Could not copy source and open the workstation. Check readiness and the configured source/import limits.')

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
    @app.post('/api/projects/{pid}/source-sync/resolve')
    async def resolve(pid:str,request:Request,body:ResolveConflict):
        try:return await links.resolve(pid,request.state.owner,body.path,body.keep)
        except (ValueError,RuntimeError,asyncio.TimeoutError):raise HTTPException(409,'The files changed or could not be synced. Refresh before resolving this conflict.')

    @app.post('/api/projects/{pid}/threads')
    async def start_chat(pid:str,request:Request):
        try:return await links.start_chat(pid,request.state.owner)
        except (ValueError,RuntimeError,asyncio.TimeoutError):raise HTTPException(503,'Could not copy source and start chat. Your existing files are intact. Check workspace readiness and source/import limits.')
    return links
