import json,time
from types import SimpleNamespace
import httpx,pytest,pytest_asyncio
from fastapi import FastAPI,Request
from chatkit.store import NotFoundError
from backend.store import SQLiteStore
from backend.projects import install_projects
from backend.workspace_links import install_workspace_links
from backend.coder import CoderAPIError
from test_projects import chat

@pytest.mark.asyncio
async def test_archive_and_recency_survive_restart_and_stale_saves(tmp_path):
    path=tmp_path/'db';s=SQLiteStore(path)
    a=await chat(s,'a',wid='wa');pa=s.ensure_project(a,'alice')
    b=await chat(s,'b',wid='wb');pb=s.ensure_project(b,'alice')
    with s.db:s.db.execute('UPDATE threads SET updated=? WHERE id=?',(time.time()+100,'a'))
    assert s.projects('alice')[0]['id']==pa['id']
    stale=await s.load_thread('a',{'owner':'alice'})
    s.archive_thread('a','alice',True);await s.save_thread(stale,{'owner':'alice'})
    with pytest.raises(ValueError):s.check_thread_writable('a','alice')
    s.update_project(pb['id'],'alice',name='Renamed',archived=True)
    s.db.close();s=SQLiteStore(path)
    assert s.get_project(pb['id'],'alice')['name']=='Renamed'
    assert not (await s.load_threads(100,None,'desc',{'owner':'alice'})).data
    assert len(s.thread_summaries('alice'))==2
    s.update_project(pb['id'],'alice',archived=False)
    assert [t.id for t in (await s.load_threads(100,None,'desc',{'owner':'alice'})).data]==['b']
    s.archive_thread('a','alice',False);s.check_thread_writable('a','alice')
    assert len(s.projects('alice'))==2

@pytest_asyncio.fixture
async def fixture(tmp_path,monkeypatch):
    import backend.project_actions as actions
    monkeypatch.setattr(actions,'STATE',tmp_path)
    s=SQLiteStore(tmp_path/'db');a=await chat(s,'a',wid='ws1');p=s.ensure_project(a,'alice');b=await chat(s,'b');s.attach_project(b,'alice',p['id'])
    state={'status':'stopped','transition':'stop','calls':[],'error':None}
    async def api(method,path,**kwargs):
        state['calls'].append((method,path))
        if state['error']:raise state['error']
        if method=='POST':state.update(status='deleting',transition='delete')
        return {'id':'ws1','template_id':'template','latest_build':{'status':state['status'],'transition':state['transition']}}
    async def live():return {'pods':[],'unavailable_namespaces':[]}
    coder=SimpleNamespace(project_locks={},active=set(),provisioning=set(),settings=lambda:{'template_id':'template'},api=api)
    app=FastAPI()
    @app.middleware('http')
    async def identity(request:Request,next):request.state.owner=request.headers.get('test-owner','alice');return await next(request)
    state['deletions']=install_projects(app,s,coder,SimpleNamespace(get=live))
    install_workspace_links(app,s,coder,SimpleNamespace())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:yield c,s,p,state,tmp_path

@pytest.mark.asyncio
async def test_routes_archive_restore_ownership_and_block_wakes(fixture):
    c,s,p,state,_=fixture;url='/api/projects/'+p['id']
    for method,path,body in [('PATCH',url,{'archived':True}),('DELETE',url,{'name':p['name']}),('PATCH','/api/threads/a',{'archived':True}),('DELETE','/api/threads/a',None)]:
        assert (await c.request(method,path,json=body,headers={'test-owner':'bob'})).status_code==404
    assert not state['calls']
    assert (await c.patch(url,json={'archived':'yes'})).status_code==422
    assert (await c.patch(url,json={'name':' '})).status_code==409
    assert (await c.patch(url,json={'archived':True})).status_code==200
    for path in ('open','threads','sync-onedrive'):assert (await c.post(url+'/'+path)).status_code==409
    assert not state['calls']
    assert (await c.patch(url,json={'archived':False})).status_code==200
    assert (await c.patch('/api/threads/a',json={'archived':True})).status_code==200
    assert s.get_project(p['id'],'alice')['workspace_id']=='ws1'

@pytest.mark.asyncio
async def test_deletion_waits_for_coder_and_preserves_history_on_failure(fixture):
    c,s,p,state,tmp=fixture;url='/api/projects/'+p['id']
    s.save_run({'id':'run_test','thread_id':'a','mode':'app'});s.remember_file('a','test.py','run_test',1)
    artifact=tmp/'artifacts'/'run_test';artifact.mkdir(parents=True);(artifact/'test.py').write_text('1')
    mirror=tmp/'mock-onedrive'/'Projects'/p['id'];mirror.mkdir(parents=True);(mirror/'file').write_text('copy')
    assert (await c.request('DELETE',url,json={'name':'wrong name'})).status_code==400
    assert not state['calls']
    state['error']=CoderAPIError(503,'offline')
    assert (await c.request('DELETE',url,json={'name':p['name']})).status_code==202
    await state['deletions'].advance(p['id'],'alice')
    assert state['deletions'].get(p['id'],'alice')['retries']==1
    assert len(s.thread_summaries('alice'))==2 and artifact.exists()
    state['error']=None
    await state['deletions'].advance(p['id'],'alice')
    assert (await c.request('DELETE',url,json={'name':p['name']})).status_code==202
    assert s.get_project(p['id'],'alice')['deleting']
    assert (await c.post(url+'/threads')).status_code==409
    with pytest.raises(ValueError):s.check_thread_writable('a','alice')
    assert (await c.request('DELETE',url,json={'name':p['name']})).status_code==202
    assert len([call for call in state['calls'] if call[0]=='POST'])==1
    assert artifact.exists()
    state['status']='deleted'
    await state['deletions'].advance(p['id'],'alice')
    assert (await c.request('DELETE',url,json={'name':p['name']})).json()['status']=='deleted'
    assert not s.projects('alice') and not s.thread_summaries('alice')
    assert not mirror.exists() and not artifact.exists()
    assert not s.db.execute('SELECT * FROM runs').fetchall()

@pytest.mark.asyncio
async def test_busy_actions_rejected_and_chat_delete_preserves_shared_home(fixture):
    c,s,p,state,_=fixture;url='/api/projects/'+p['id']
    job={'id':'j','owner':'alice','thread_id':'a','status':'running','started':time.time()};s.save_job(job)
    for method,path,body in [('PATCH',url,{'archived':True}),('DELETE',url,{'name':p['name']}),('PATCH','/api/threads/a',{'archived':True}),('DELETE','/api/threads/a',None)]:
        assert (await c.request(method,path,json=body)).status_code==409
    assert not state['calls']
    job['status']='completed';s.save_job(job)
    assert (await c.delete('/api/threads/a')).status_code==200
    assert not state['calls']
    assert s.get_project(p['id'],'alice')['workspace_id']=='ws1'
    assert [t['id'] for t in s.projects('alice')[0]['threads']]==['b']

@pytest.mark.asyncio
async def test_missing_workspace_and_failed_build_are_retryable(fixture):
    c,s,p,state,_=fixture;url='/api/projects/'+p['id'];worker=state['deletions']
    assert (await c.request('DELETE',url,json={'name':p['name']})).status_code==202
    await worker.advance(p['id'],'alice')
    state['status']='failed'
    await worker.advance(p['id'],'alice')
    result=(await c.get(url+'/deletion')).json()
    assert result['status']=='failed' and 'Coder' in result['error']
    await worker.advance(p['id'],'alice')
    assert len([x for x in state['calls'] if x[0]=='POST'])==1
    assert (await c.request('DELETE',url,json={'name':p['name']})).status_code==202
    await worker.advance(p['id'],'alice')
    assert len([x for x in state['calls'] if x[0]=='POST'])==2
    state['error']=CoderAPIError(410,'removed')
    await worker.advance(p['id'],'alice')
    assert (await c.get(url+'/deletion')).json()['status']=='deleted'
    assert not s.projects('alice')

@pytest.mark.asyncio
async def test_migrated_project_recency_uses_chat_activity_not_migration_time(tmp_path):
    s=SQLiteStore(tmp_path/'db');await chat(s,'older',wid='old-ws');await chat(s,'newer',wid='new-ws')
    with s.db:
        s.db.execute('UPDATE threads SET updated=10 WHERE id=?',('older',))
        s.db.execute('UPDATE threads SET updated=20 WHERE id=?',('newer',))
    s.migrate_projects()
    assert [p['threads'][0]['id'] for p in s.projects('alice')]==['newer','older']

@pytest.mark.asyncio
async def test_unallocated_project_does_not_inherit_control_plane_status(tmp_path):
    s=SQLiteStore(tmp_path/'db');a=await chat(s,'a');p=s.ensure_project(a,'alice');app=FastAPI()
    @app.middleware('http')
    async def identity(request:Request,next):request.state.owner='alice';return await next(request)
    async def live():return {'pods':[{'namespace':'lab-agents','workspace_id':None,'state':'running'}],'unavailable_namespaces':[]}
    install_projects(app,s,SimpleNamespace(project_locks={}),SimpleNamespace(get=live))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        assert (await c.get('/api/projects')).json()[0]['status']=='not started'

@pytest.mark.asyncio
async def test_status_is_read_only_and_deletion_resumes_after_restart(fixture):
    from backend.project_deletions import ProjectDeletions
    c,s,p,state,_=fixture;url='/api/projects/'+p['id'];old=state['deletions']
    await c.request('DELETE',url,json={'name':p['name']})
    for _ in range(3):assert (await c.get(url+'/deletion')).json()['status']=='deleting'
    assert not state['calls']
    assert (await c.get(url+'/deletion',headers={'test-owner':'bob'})).status_code==404
    replacement=ProjectDeletions(s,old.step)
    await replacement.advance(p['id'],'alice')
    assert len([x for x in state['calls'] if x[0]=='POST'])==1
    state['error']=CoderAPIError(410,'gone')
    await replacement.advance(p['id'],'alice')
    assert not s.projects('alice')
    assert replacement.get(p['id'],'alice')['status']=='deleted'
    assert (await c.request('DELETE',url,json={'name':p['name']})).json()['status']=='deleted'

@pytest.mark.asyncio
async def test_deletion_waits_for_provisioning_then_finishes_without_browser(fixture):
    import asyncio
    c,s,p,state,_=fixture;url='/api/projects/'+p['id'];worker=state['deletions']
    state.update(status='starting',transition='start')
    await c.request('DELETE',url,json={'name':p['name']})
    await worker.advance(p['id'],'alice')
    assert worker.get(p['id'],'alice')['status']=='deleting'
    assert not [x for x in state['calls'] if x[0]=='POST']
    state.update(status='deleted',transition='delete')
    worker.update(p['id'],'Checking deletion',delay=0)
    task=asyncio.create_task(worker.maintain())
    try:
        for _ in range(100):
            if worker.get(p['id'],'alice')['status']=='deleted':break
            await asyncio.sleep(.01)
        assert worker.get(p['id'],'alice')['status']=='deleted'
        assert not s.projects('alice')
    finally:
        task.cancel();await asyncio.gather(task,return_exceptions=True)

@pytest.mark.asyncio
async def test_project_list_uses_constant_queries_and_keeps_owner_boundary(tmp_path):
    s=SQLiteStore(tmp_path/'db')
    for n in range(20):
        t=await chat(s,'a'+str(n));s.ensure_project(t,'alice')
    t=await chat(s,'secret','bob');s.ensure_project(t,'bob')
    queries=[];s.db.set_trace_callback(queries.append)
    result=s.projects('alice');s.db.set_trace_callback(None)
    assert len(result)==20 and all(p['threads'][0]['id']!='secret' for p in result)
    assert len([q for q in queries if q.startswith('SELECT')])==2
