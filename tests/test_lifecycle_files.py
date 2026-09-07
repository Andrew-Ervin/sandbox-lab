import asyncio,base64,importlib.util,json,time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from backend import checkpoints
from backend.live import runtime


def test_quick_checkpoints_persist_isolate_and_reject_paths(tmp_path,monkeypatch):
    monkeypatch.setattr(checkpoints,'STATE',tmp_path)
    entry=lambda name,data:{'name':name,'data':base64.b64encode(data).decode()}
    checkpoints.save('alice-chat','run-a',{'files':[entry('data/table.csv',b'1,2'),entry('main.py',b'print(1)')]})
    checkpoints.save('bob-chat','run-b',{'files':[entry('data/table.csv',b'3,4')]})
    assert checkpoints.load('alice-chat')[0]['data']==base64.b64encode(b'1,2').decode()
    assert checkpoints.load('bob-chat')[0]['data']==base64.b64encode(b'3,4').decode()
    assert checkpoints.load('new-chat')==[]
    for path in ['../escape','a/../../escape','/tmp/escape','.env','node_modules/foo','data/.secret']:
        with pytest.raises(ValueError):checkpoints.save('alice-chat','run-x',{'files':[entry(path,b'no')]})
    assert len(checkpoints.load('alice-chat'))==2


def test_pod_checkpoint_ignores_symlinks_and_roundtrips_nested_files(tmp_path):
    spec=importlib.util.spec_from_file_location('checkpoint',Path(__file__).parents[1]/'sandbox/checkpoint.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    root=tmp_path/'work';root.mkdir();(root/'data').mkdir();(root/'data/a.csv').write_text('42')
    (root/'escape').symlink_to('/etc/passwd');(root/'escape-dir').symlink_to('/etc',target_is_directory=True)
    (root/'.env').write_text('private');(root/'artifacts').mkdir();(root/'artifacts/a.png').write_text('skip')
    saved=m.collect_checkpoint(str(root));assert [e['name'] for e in saved['files']]==['data/a.csv']
    fresh=tmp_path/'fresh';fresh.mkdir();m.restore(saved['files'],str(fresh));assert (fresh/'data/a.csv').read_text()=='42'


def test_runtime_uses_pods_instead_of_historical_build_success():
    live={'pods':[],'unavailable_namespaces':[]}
    assert runtime('w','running',live,'lab-dev')=='stopped'
    live['pods']=[{'namespace':'lab-dev','workspace_id':'w','state':'stopping'}]
    assert runtime('w','running',live,'lab-dev')=='stopping'
    live['unavailable_namespaces']=['lab-dev']
    assert runtime('w','running',live,'lab-dev')=='unknown'

@pytest.mark.asyncio
async def test_connection_traffic_does_not_extend_idle_but_real_editor_activity_does():
    from backend.idle import IdleWorkspaces
    stopped=[]
    def adapter(names):
        async def api(method,path,**kwargs):
            if method=='GET':return {'workspaces':[{'id':n,'last_used_at':datetime.now(timezone.utc).isoformat(),'latest_build':{'status':'running','updated_at':'2020-01-01T00:00:00Z'}} for n in names]}
            stopped.append(path.split('/')[-2])
        return SimpleNamespace(api=api,touched={},tasks={},active=set())
    c=adapter(['ai-idle']);d=adapter(['typing','dev-idle'])
    async def activity(wid):return time.time() if wid=='typing' else 0
    d.activity=activity
    idle=IdleWorkspaces(c,d,SimpleNamespace(active_workspaces=lambda:set()));idle.started=0
    await idle.reap();assert set(stopped)=={'ai-idle','dev-idle'}

@pytest.mark.asyncio
async def test_chat_and_quick_never_allocate_a_project(tmp_path,monkeypatch):
    from backend.chat import LabChat,coder,compute
    from backend.store import SQLiteStore
    store=SQLiteStore(tmp_path/'db');chat=LabChat(store)
    import backend.chat as chatmodule
    monkeypatch.setattr(chatmodule,'STATE',tmp_path)
    async def forbidden(*a,**kw):raise AssertionError('No project should be allocated')
    monkeypatch.setattr(coder,'run',forbidden);monkeypatch.setattr(coder,'workspace',forbidden)
    responses=iter([{'role':'assistant','content':'Hello'}, {'role':'assistant','tool_calls':[{'id':'c','function':{'name':'run_python','arguments':json.dumps({'code':'print(42)','purpose':'sum'})}}]}, {'role':'assistant','content':'42'}])
    async def completion(*a,**kw):return next(responses)
    async def quick(*a,**kw):return {'stdout':'42','exit_code':0,'artifacts':[]}
    monkeypatch.setattr(chat,'completion',completion);monkeypatch.setattr(compute,'quick',quick)
    for message in ['Hello','Calculate']:
        result=await chat.process(json.dumps({'type':'threads.create','params':{'input':{'content':[{'type':'input_text','text':message}],'attachments':[],'inference_options':{}}}}).encode(),{'owner':'a','mode':'auto'})
        async for _ in result:pass
    page=await store.load_threads(10,None,'asc',{'owner':'a'})
    assert len(page.data)==2 and all(not t.metadata.get('coder_workspace_id') for t in page.data)
