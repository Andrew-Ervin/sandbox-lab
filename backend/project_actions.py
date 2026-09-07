"""Owner-scoped project/chat actions. Deletion is retryable until Coder confirms it."""
import asyncio,json,re,shutil,httpx
from fastapi import HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,StrictBool
from chatkit.store import NotFoundError
from .coder import CoderAPIError
from .config import STATE
from .project_deletions import ProjectDeletions,active_threads,cleanup_paths,remove_paths,purge_records

class ProjectUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str|None=None
    archived:StrictBool|None=None

class ProjectDelete(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str

class ThreadUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    archived:StrictBool


def install_project_actions(app,store,coder):
    def owned(pid,owner):
        try:return store.get_project(pid,owner)
        except NotFoundError:raise HTTPException(404,'Project not found')

    def idle(tids,owner):
        if active_threads(store,tids,owner):raise HTTPException(409,'A conversation is running. Wait for it to finish or stop its run first.')

    def purge(tids):
        remove_paths(cleanup_paths(store,tids,STATE))
        with store.db:purge_records(store,tids)

    @app.patch('/api/projects/{pid}')
    async def update_project(pid:str,request:Request,body:ProjectUpdate):
        owner=request.state.owner;owned(pid,owner)
        tids={r[0] for r in store.db.execute('SELECT thread FROM project_threads WHERE project=?',(pid,))}
        if body.archived:idle(tids,owner)
        if coder.project_locks.setdefault(pid,asyncio.Lock()).locked():raise HTTPException(409,'This project is busy. Try again after the operation finishes.')
        try:store.update_project(pid,owner,name=body.name,archived=body.archived)
        except ValueError as exc:raise HTTPException(409,str(exc))
        return store.get_project(pid,owner)

    @app.patch('/api/threads/{tid}')
    async def update_thread(tid:str,request:Request,body:ThreadUpdate):
        try:
            await store.load_thread(tid,{'owner':request.state.owner})
            p=store.project_for_thread(tid,request.state.owner)
            if p and p['deleting']:raise HTTPException(409,'Project deletion is in progress')
            if body.archived:idle({tid},request.state.owner)
            store.archive_thread(tid,request.state.owner,body.archived)
        except NotFoundError:raise HTTPException(404,'Conversation not found')
        return {'id':tid,'archived':body.archived}

    @app.delete('/api/threads/{tid}')
    async def delete_thread(tid:str,request:Request):
        try:await store.load_thread(tid,{'owner':request.state.owner})
        except NotFoundError:raise HTTPException(404,'Conversation not found')
        p=store.project_for_thread(tid,request.state.owner)
        if p and (p['deleting'] or coder.project_locks.setdefault(p['id'],asyncio.Lock()).locked()):raise HTTPException(409,'This project is busy. Try again after the operation finishes.')
        idle({tid},request.state.owner);purge({tid})
        return {'status':'deleted'}

    async def delete_step(pid,owner,operation):
        p=owned(pid,owner)
        tids={r[0] for r in store.db.execute('SELECT thread FROM project_threads WHERE project=?',(pid,))}
        idle(tids,owner)
        lock=coder.project_locks.setdefault(pid,asyncio.Lock())
        if lock.locked():raise HTTPException(409,'This project is busy. Try again after the operation finishes.')
        async with lock:
            wid=p['workspace_id']
            if wid:
                if wid in coder.active or wid in coder.provisioning:raise HTTPException(409,'The workspace is busy. Wait for it to finish.')
                try:
                    try:ws=await coder.api('GET','/api/v2/workspaces/'+wid)
                    except CoderAPIError as exc:
                        if exc.status_code not in (404,410):raise
                        ws={'deleted':True}
                    if not ws.get('deleted') and ws.get('latest_build',{}).get('status')!='deleted':
                        if ws['template_id']!=coder.settings()['template_id']:raise HTTPException(403,'Headless template mismatch')
                        status=ws['latest_build']['status']
                        if status in ('starting','stopping','pending','canceling'):raise HTTPException(409,'Waiting for the current workspace operation to finish')
                        if status in ('failed','canceled') and ws['latest_build'].get('transition')=='delete' and operation['submitted']:
                            raise HTTPException(422,'Coder could not delete the workspace. Inspect its failed build, then retry deletion.')
                        tids={r[0] for r in store.db.execute('SELECT thread FROM project_threads WHERE project=?',(pid,))}
                        idle(tids,owner)
                        if wid in coder.active or wid in coder.provisioning:raise HTTPException(409,'The workspace is busy. Wait for it to finish.')
                        if status!='deleting':
                            deletions.submitted(pid)
                            await coder.api('POST','/api/v2/workspaces/'+wid+'/builds',json={'transition':'delete'})
                        return {'status':'deleting','phase':'Deleting workspace and its storage'}
                except (RuntimeError,asyncio.TimeoutError,httpx.HTTPError):raise HTTPException(503,'Coder could not confirm deletion. Project history retained; retry deletion to continue.')
            tids={r[0] for r in store.db.execute('SELECT thread FROM project_threads WHERE project=?',(pid,))}
            idle(tids,owner)
            # Coder has confirmed removal. Disk cleanup runs off the request/event loop.
            paths=cleanup_paths(store,tids,STATE)
            if re.fullmatch(r'prj_[a-f0-9]{32}',pid):paths.append(STATE/'mock-onedrive'/'Projects'/pid)
            await asyncio.to_thread(remove_paths,paths)
            with store.db:
                purge_records(store,tids)
                store.db.execute('DELETE FROM projects WHERE id=? AND owner=?',(pid,owner))
                # Commit completion with the deletion so a crash cannot strand the operation.
                deletions.update(pid,'Project deleted',status='deleted')
            return {'status':'deleted','phase':'Project deleted'}

    deletions=ProjectDeletions(store,delete_step)

    @app.delete('/api/projects/{pid}')
    async def delete_project(pid:str,request:Request,body:ProjectDelete):
        try:
            p=store.get_project(pid,request.state.owner)
            if coder.project_locks.setdefault(pid,asyncio.Lock()).locked():raise HTTPException(409,'This project is busy. Try again after the operation finishes.')
        except NotFoundError:
            try:deletions.get(pid,request.state.owner)
            except NotFoundError:raise HTTPException(404,'Project not found')
        try:result=deletions.queue(pid,request.state.owner,body.name)
        except NotFoundError:raise HTTPException(404,'Project not found')
        return JSONResponse(result,status_code=200 if result['status']=='deleted' else 202)

    @app.get('/api/projects/{pid}/deletion')
    async def deletion_status(pid:str,request:Request):
        try:return deletions.public(deletions.get(pid,request.state.owner))
        except NotFoundError:raise HTTPException(404,'Deletion not found')

    return deletions
