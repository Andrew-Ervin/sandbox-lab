import secrets
import os
import time
import asyncio
import re
import json
from contextlib import asynccontextmanager
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse, FileResponse, RedirectResponse
from chatkit.server import StreamingResult
from .store import SQLiteStore
from .chat import LabChat
from .compute import compute
from .coder import coder
from .previews import previews
from .config import STATE
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .config import API_KEY, DOMAIN_KEY, MODEL, REASONING
from .jobs import Jobs
from .developer import developer
from .health import HealthCache
from .idle import IdleWorkspaces
from .apps import apps
from . import package_policy
from .live import live_containers,runtime
store = SQLiteStore()
chat_server = LabChat(store)
jobs = Jobs(store)
health = HealthCache()
idle = IdleWorkspaces(coder,developer,previews)
@asynccontextmanager
async def lifespan(app):
    store.recover_jobs()
    store.migrate_projects()
    migration=STATE/'ui-migration-v5.done'
    if not migration.exists():
        # Saved links resolve through authenticated routes, even after a backend restart.
        all_runs=store.runs('local-owner',-1)
        by_thread={}
        for r in all_runs: by_thread.setdefault(r['thread_id'],[]).append(r)
        for run in reversed(all_runs):
            for a in run.get('artifacts',[]): a['url']=f'/api/artifact-view/{run["id"]}/{a["name"]}'
            for a in run.get('artifacts',[]):
                path=STATE/'artifacts'/run['id']/a['name']
                if path.is_file() and not path.is_symlink(): store.remember_file(run['thread_id'],a['name'],run['id'],path.stat().st_size)
            if run.get('preview_url') and run.get('workspace_id'): run['preview_url']=f'/api/app-preview/{run["id"]}'
            store.save_run(run)
        # Older ChatKit links were relative to the CDN iframe or an expired preview port.
        for thread in (await store.load_threads(1000,None,'asc',{'owner':'local-owner'})).data:
            runs=[r for r in by_thread.get(thread.id,[]) if r.get('preview_url')]
            page=await store.load_thread_items(thread.id,None,1000,'asc',{'owner':'local-owner'})
            current_run=None
            for item in page.data:
                if item.type=='task' and item.id.startswith('exec_run_'):
                    current_run=store.get_run(item.id.removeprefix('exec_'),'local-owner')
                if item.type=='widget' and current_run:
                    children=getattr(item.widget,'children',[])
                    name=getattr(children[0],'value',None) if children else None
                    artifact=next((a for a in current_run.get('artifacts',[]) if a['name']==name),None)
                    if artifact:
                        replacement=chat_server.artifact_widget(thread,current_run,artifact)
                        replacement.id=item.id; replacement.created_at=item.created_at
                        await store.save_item(thread.id,replacement,{'owner':'local-owner'})
                    elif name=='Your app is ready' and current_run.get('preview_url'):
                        from chatkit.widgets import Button
                        item.widget.theme='dark'; item.widget.background='surface-secondary'
                        item.widget.children=[children[0],Button(label='Open app',onClickAction={'type':'open_app','handler':'client','payload':{'run_id':current_run['id']}})]
                        await store.save_item(thread.id,item,{'owner':'local-owner'})
                if item.type!='assistant_message': continue
                changed=False
                for part in item.content:
                    if not hasattr(part,'text'): continue
                    text=re.sub(r'\]\((/api/(?:artifacts|artifact-view|app-preview)/[^)]+)\)',r'](http://127.0.0.1:3000\1)',part.text)
                    if runs: text=re.sub(r'\[Open app preview\]\(http://127\.0\.0\.1:\d+/\)',f'[Open app preview](http://127.0.0.1:3000{runs[0]["preview_url"]})',text)
                    if text!=part.text: part.text=text; changed=True
                if changed: await store.save_item(thread.id,item,{'owner':'local-owner'})
        migration.write_text('complete')
    task=asyncio.create_task(compute.maintain())
    preview_task=asyncio.create_task(previews.maintain())
    idle_task=asyncio.create_task(idle.maintain())
    reserve_task=asyncio.create_task(coder.reserve.maintain(store))
    deletion_task=asyncio.create_task(project_deletions.maintain())
    links_task=asyncio.create_task(workspace_links.maintain())
    links_migration=asyncio.create_task(workspace_links.migrate())
    yield
    await jobs.close()
    await chat_server.close()
    task.cancel();preview_task.cancel();idle_task.cancel();reserve_task.cancel();deletion_task.cancel();links_task.cancel();links_migration.cancel()
    await asyncio.gather(task,preview_task,idle_task,reserve_task,deletion_task,links_task,links_migration,return_exceptions=True)
    await previews.close()
app = FastAPI(title='Sandbox Lab', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
sessions = {}
# Optional local experiment routes use the same session/CSRF middleware.
from .experiments import experiment
experiment.install(app,sessions,store)
from .projects import install_projects
project_deletions=install_projects(app,store,coder,live_containers)
from .workspace_links import install_workspace_links
workspace_links=install_workspace_links(app,store,coder,developer)
ALLOWED_HOSTS = {'127.0.0.1:3000', 'localhost:3000', '127.0.0.1:8787', 'localhost:8787'}
ALLOWED_ORIGINS = {'http://' + h for h in ALLOWED_HOSTS}
@app.middleware('http')
async def local_security(request: Request, call_next):
    if request.headers.get('host') not in ALLOWED_HOSTS:
        return JSONResponse({'detail':'Untrusted host'}, 403)
    if request.headers.get('origin') and request.headers['origin'] not in ALLOWED_ORIGINS:
        return JSONResponse({'detail':'Untrusted origin'}, 403)
    if request.url.path != '/api/bootstrap':
        token = request.cookies.get('lab_session', '')
        entry = sessions.get(token)
        if not entry or entry['expires'] < time.time():
            return JSONResponse({'detail':'Reload to start a local session'}, 401)
        if request.method != 'GET' and not secrets.compare_digest(request.headers.get('x-lab-csrf', ''), entry['csrf']):
            return JSONResponse({'detail':'Invalid CSRF token'}, 403)
        request.state.owner = 'local-owner'
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response
@app.post('/api/bootstrap')
async def bootstrap(request: Request):
    now = time.time()
    for key in list(sessions):
        if sessions[key]['expires'] < now: sessions.pop(key)
    token = request.cookies.get('lab_session', '')
    if token not in sessions:
        token = secrets.token_urlsafe(32)
        sessions[token] = {'csrf':secrets.token_urlsafe(32), 'expires':now+86400}
    response = JSONResponse({'csrf':sessions[token]['csrf'], 'domain_key':DOMAIN_KEY})
    response.set_cookie('lab_session', token, httponly=True, samesite='strict', max_age=86400)
    return response
@app.get('/api/status')
async def status(request: Request):
    infrastructure,live=await asyncio.gather(health.get(compute,coder),live_containers.get())
    runs=store.runs(request.state.owner,details=False)
    app_runs=store.apps(request.state.owner)
    for run in runs+app_runs:
        run['runtime_status']='static' if run.get('preview_artifact') else runtime(run.get('workspace_id'),None,live,'lab-agents') if run.get('workspace_id') else ('running' if any(p['name']==run.get('pod') for p in live['pods']) else 'released')
    return {'project_reserve':coder.reserve.status(),'containers':live,'idle_policy':{'project_seconds':idle.project_idle,'developer_seconds':idle.developer_idle,'error':idle.error},**infrastructure, 'openrouter':bool(API_KEY), 'model':MODEL, 'reasoning':REASONING, 'coding_engine':os.getenv('PROJECT_ENGINE','ori-pi'), 'pool':compute.status(), 'idle_workspaces_stopped':idle.stopped, 'runs':runs,'apps':app_runs,'jobs':[{k:v for k,v in j.items() if k!='owner'} for j in store.jobs(request.state.owner)]}
@app.get('/api/threads')
async def threads(request: Request):
    return store.thread_summaries(request.state.owner)

@app.get('/api/approval-payload/{thread_id}/{item_id}')
async def approval_payload(thread_id:str,item_id:str,request:Request):
    from chatkit.store import NotFoundError
    try:item=await store.load_item(thread_id,item_id,{'owner':request.state.owner})
    except NotFoundError:raise HTTPException(404,'Request not found')
    if item.type!='widget' or not item.copy_text:raise HTTPException(404,'No request payload available')
    raw=item.copy_text.encode()
    if len(raw)>100_000:raise HTTPException(413,'Request is too large to preview')
    return {'url':await previews.document(item_id,'Full request.json',raw)}

@app.get('/api/package-policy')
async def read_package_policy():return package_policy.read()

@app.post('/api/package-policy')
async def write_package_policy(request: Request):
    return await package_policy.change(await request.json(),request.state.owner)

@app.post('/api/chatkit')
async def chatkit(request: Request):
    body=await request.body()
    if len(body)>128000: raise HTTPException(413,'Message too large')
    mode=request.headers.get('x-lab-mode','auto')
    if mode not in ['auto','quick','analysis','app']: raise HTTPException(400,'Unknown execution mode')
    try: parsed=json.loads(body)
    except ValueError: raise HTTPException(400,'Invalid request')
    if parsed.get('type') in ['threads.create','threads.add_user_message','threads.retry_after_item'] and len(jobs.tasks)>=jobs.max_pending:
        raise HTTPException(429,'The local job queue is full. Retry after a running task finishes.')
    thread_id=parsed.get('params',{}).get('thread_id')
    if thread_id and parsed.get('type') in ['threads.add_user_message','threads.retry_after_item','threads.delete']:
        await store.load_thread(thread_id,{'owner':request.state.owner})
        if jobs.active(request.state.owner,thread_id): raise HTTPException(409,'This conversation is running. Wait or use Stop run.')
    if thread_id and parsed.get('type') in ['threads.add_user_message','threads.retry_after_item','threads.custom_action']:
        try:store.check_thread_writable(thread_id,request.state.owner)
        except ValueError as exc:raise HTTPException(409,str(exc))
    context={'owner':request.state.owner,'mode':mode}
    result=await chat_server.process(body,context)
    if isinstance(result,StreamingResult):
        return StreamingResponse(jobs.start(result,context,thread_id),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
    return Response(content=result.json,media_type='application/json')
@app.get('/api/artifacts/{run_id}/{filename}')
async def artifact(run_id: str, filename: str, request: Request):
    run=store.get_run(run_id,request.state.owner)
    if not run or filename not in [a['name'] for a in run.get('artifacts',[])]: raise HTTPException(404)
    path=STATE/'artifacts'/run_id/filename
    if not path.is_file() or path.is_symlink(): raise HTTPException(404)
    # HTML/JS/SVG is always downloaded. It is never rendered on the trusted chat origin.
    return FileResponse(path,filename=filename,media_type='application/octet-stream',headers={'Content-Security-Policy':"sandbox; default-src 'none'"})

@app.get('/api/artifact-view/{run_id}/{filename}')
async def artifact_view(run_id: str, filename: str, request: Request):
    run=store.get_run(run_id,request.state.owner)
    if not run or filename not in [a['name'] for a in run.get('artifacts',[])]: raise HTTPException(404)
    path=STATE/'artifacts'/run_id/filename
    if not path.is_file() or path.is_symlink(): raise HTTPException(404)
    target=await previews.artifact(path)
    url=target or f'/api/artifacts/{run_id}/{filename}'
    return {'url':url,'preview':bool(target)} if request.query_params.get('resolve') else RedirectResponse(url)

@app.get('/api/app-preview/{run_id}')
async def app_preview(run_id: str, request: Request):
    run=store.get_run(run_id,request.state.owner)
    if not run or run.get('mode')!='app': raise HTTPException(404)
    if run.get('preview_artifact'):
        name=run['preview_artifact']
        if name not in [a['name'] for a in run.get('artifacts',[])]: raise HTTPException(404)
        path=STATE/'artifacts'/run_id/name
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_. -]{0,159}',name) or '..' in name or not path.is_file() or path.is_symlink(): raise HTTPException(404)
        url=await previews.artifact(path)
        if not url: raise HTTPException(404)
        return {'url':url} if request.query_params.get('resolve') else RedirectResponse(url)
    if not run.get('workspace_id'): raise HTTPException(404)
    ws=await coder.api('GET','/api/v2/workspaces/'+run['workspace_id'])
    if ws['template_id']!=coder.settings()['template_id']: raise HTTPException(403)
    if ws['latest_build']['status']!='running': raise HTTPException(409,'Workspace is asleep. Open or reload this app to resume it automatically.')
    url=await previews.app(ws,coder.settings())
    coder.touched[ws['id']]=time.time()
    return {'url':url} if request.query_params.get('resolve') else RedirectResponse(url)

@app.post('/api/apps/{run_id}/start')
async def start_app(run_id: str, request: Request):
    run=store.get_run(run_id,request.state.owner)
    if not run or run.get('mode')!='app':raise HTTPException(404)
    if run.get('preview_artifact'):return await app_preview(run_id,request)
    if not run.get('workspace_id'):raise HTTPException(404)
    try:return {'url':await apps.ai(run,store,request.state.owner,coder,previews)}
    except ValueError as exc:raise HTTPException(403,str(exc))
    except RuntimeError as exc:raise HTTPException(503,str(exc))

@app.post('/api/developer/workspaces/{workspace_id}/resume')
async def resume_developer(workspace_id: str, request: Request):
    data=await request.json()
    try:url=await apps.human(workspace_id,developer,previews,ide=data.get('ide',True))
    except ValueError as exc:raise HTTPException(404,str(exc))
    except RuntimeError as exc:raise HTTPException(503,str(exc))
    response=JSONResponse({'url':url})
    response.set_cookie('coder_session_token',developer.token,httponly=True,samesite='lax',max_age=86400)
    return response

@app.post('/api/threads/{thread_id}/stop')
async def stop_thread(thread_id: str, request: Request):
    await store.load_thread(thread_id,{'owner':request.state.owner})
    await jobs.stop(request.state.owner,thread_id)
    return {'stopped':True}

@app.get('/api/threads/{thread_id}/files')
async def thread_files(thread_id: str,request: Request):
    thread=await store.load_thread(thread_id,{'owner':request.state.owner})
    return {'files':store.files(thread_id),'workspace_id':thread.metadata.get('coder_workspace_id'),
            'quick':'Fresh interpreter; local working-file checkpoint restored to /workspace; selected artifacts restored to /workspace/files.',
            'project_id':(store.project_for_thread(thread_id,request.state.owner) or {}).get('id'),'packages':'Project conversations share their Coder home, source files, packages and caches.'}

@app.get('/api/runs/{run_id}')
async def run_detail(run_id: str, request: Request):
    run=store.get_run(run_id,request.state.owner)
    if not run: raise HTTPException(404)
    return run

@app.get('/api/developer/workspaces')
async def developer_workspaces(request:Request):
    try:
        workspaces=await developer.list();live=await live_containers.get()
        linked={wid:{'id':pid,'name':name} for wid,pid,name in store.db.execute('SELECT developer_workspace_id,id,name FROM projects WHERE owner=? AND developer_workspace_id IS NOT NULL',(request.state.owner,))}
        for ws in workspaces:
            ws['coder_status']=ws['status'];ws['status']=runtime(ws['id'],ws['status'],live,'lab-dev');ws['observed_at']=live['observed_at']
            p=linked.get(ws['id'])
            ws['project_id']=p['id'] if p else None;ws['project_name']=p['name'] if p else None
        return workspaces
    except Exception: raise HTTPException(503,'Developer Coder is not available')

@app.post('/api/developer/workspaces')
async def developer_start(request: Request):
    data=await request.json()
    try:
        workspace=await developer.start(data.get('name','dev'))
        project=store.link_developer(workspace['id'],request.state.owner,workspace['name'])
        workspace.update(project_id=project['id'],project_name=project['name'])
        response=JSONResponse(workspace)
        response.set_cookie('coder_session_token',developer.token,httponly=True,samesite='lax',max_age=86400)
        return response
    except ValueError as exc: raise HTTPException(400,str(exc))
    except Exception: raise HTTPException(503,'Could not start the developer workspace; check the developer portal')

@app.delete('/api/developer/workspaces/{workspace_id}')
async def developer_delete(workspace_id: str,request:Request):
    try:
        p=store.developer_project(workspace_id,request.state.owner)
        lock=coder.project_locks.setdefault(p['id'],asyncio.Lock()) if p else asyncio.Lock()
        if lock.locked():raise HTTPException(409,'Wait for this project’s sync operation to finish')
        async with lock:
            result=await developer.delete(workspace_id)
            with store.db:store.db.execute('UPDATE projects SET developer_workspace_id=NULL,developer_name=NULL WHERE developer_workspace_id=? AND owner=?',(workspace_id,request.state.owner))
            return result
    except HTTPException:raise
    except LookupError: raise HTTPException(404,'Workspace not found')
    except ValueError as exc: raise HTTPException(409,str(exc))
    except Exception: raise HTTPException(503,'Could not delete the workspace. Refresh its status and retry.')

@app.get('/api/developer/workspaces/{workspace_id}/open')
async def developer_open(workspace_id: str, resolve: bool = False):
    workspace=next((w for w in await developer.list() if w['id']==workspace_id),None)
    if not workspace: raise HTTPException(404)
    if workspace['status']!='running': raise HTTPException(409,'Start the developer workspace before opening VS Code.')
    try: await developer.prepare(workspace)
    except RuntimeError as exc: raise HTTPException(503,str(exc))
    response=JSONResponse({'url':workspace['ide_url']}) if resolve else RedirectResponse(workspace['ide_url'])
    response.set_cookie('coder_session_token',developer.token,httponly=True,samesite='lax',max_age=86400)
    return response

@app.get('/api/developer/workspaces/{workspace_id}/preview')
async def developer_preview(workspace_id: str, resolve: bool = False):
    workspace=next((w for w in await developer.list() if w['id']==workspace_id),None)
    if not workspace: raise HTTPException(404)
    if workspace['status']!='running': raise HTTPException(409,'Start the developer workspace before opening its app.')
    developer.touched[workspace_id]=time.time()
    try:
        url=await previews.app(workspace,{'token':developer.token},coder_url='http://127.0.0.1:7080')
    except RuntimeError as exc: raise HTTPException(503,str(exc))
    return JSONResponse({'url':url}) if resolve else RedirectResponse(url)

@app.post('/api/developer/workspaces/{workspace_id}/harness')
async def developer_harness(workspace_id: str):
    workspace=next((w for w in await developer.list() if w['id']==workspace_id),None)
    if not workspace: raise HTTPException(404)
    developer.configure(workspace_id,workspace['name'])
    return {'status':'Preparing Ori / Pi'}

@app.post('/api/compute/warm')
async def prewarm_compute():
    compute.policy.warm();compute.refill.set()
    return {'warming':True,'pool':compute.status()}

@app.post('/api/developer/workspaces/{workspace_id}/heartbeat')
async def developer_heartbeat(workspace_id: str):
    workspace=next((w for w in await developer.list() if w['id']==workspace_id),None)
    if not workspace: raise HTTPException(404)
    developer.touched[workspace_id]=time.time()
    return {'active':True}
