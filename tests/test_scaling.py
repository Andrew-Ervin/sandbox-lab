import asyncio,time
from types import SimpleNamespace
import pytest
from backend.scaling import WarmPolicy
from backend.compute import Compute
from backend.idle import IdleWorkspaces


def test_reserve_grows_with_bursts_and_reaches_zero_only_when_idle():
    now=[0.];p=WarmPolicy(base=2,maximum=6,idle_seconds=20,clock=lambda:now[0])
    assert p.reserve()==0
    p.warm(5);assert p.reserve()==2
    for _ in range(30):p.arrival()
    p.observe_refill(8);assert p.reserve()==6
    now[0]=100
    assert p.reserve(busy=1)>=2
    assert p.reserve()==0
    p.arrival();assert p.reserve()==2


def pod(name,state='warm',phase='Running'):
    return SimpleNamespace(metadata=SimpleNamespace(name=name,labels={'lab/state':state},resource_version='1',deletion_timestamp=None),status=SimpleNamespace(phase=phase,container_statuses=[]))

@pytest.mark.asyncio
async def test_pool_cap_and_idle_drain_never_delete_leased_pods(monkeypatch):
    c=Compute();c.max_pods=4;c.initialized=True;c.policy.warm();c.acquiring=20
    deleted=[]
    async def call(method,*args,**kwargs):
        if method=='create_namespaced_pod':return pod(args[1]['metadata']['name'])
        if method=='patch_namespaced_pod':
            assert args[2]['metadata']['resourceVersion']=='1'
            assert c.cache[args[0]].metadata.labels['lab/state']=='warm'
            c.cache[args[0]].metadata.labels['lab/state']='retiring'
        if method=='delete_namespaced_pod':deleted.append(args[0])
    monkeypatch.setattr(c,'call',call)
    await c.replenish();assert len(c.cache)==4
    protected=list(c.cache)[:2]
    for n in protected:c.cache[n].metadata.labels['lab/state']='leased'
    c.acquiring=0;c.policy.last_activity=None;c.policy.warm_until=0
    await c.replenish()
    assert set(c.cache)==set(protected) and not set(deleted)&set(protected)

@pytest.mark.asyncio
async def test_ready_event_wakes_cold_acquisition_without_poll_interval(monkeypatch):
    c=Compute();c.initialized=True;c.max_pods=1;created=asyncio.Event()
    async def call(method,*args,**kwargs):
        if method=='create_namespaced_pod':created.set();return pod(args[1]['metadata']['name'],phase='Pending')
        if method=='patch_namespaced_pod':return pod(args[0],'leased')
    monkeypatch.setattr(c,'call',call)
    task=asyncio.create_task(c.acquire())
    await asyncio.wait_for(created.wait(),.5)
    name=next(iter(c.cache));c.event({'type':'MODIFIED','object':pod(name)})
    assert await asyncio.wait_for(task,.5)==name
    assert c.cold_misses==1 and c.acquiring==0

@pytest.mark.asyncio
async def test_idle_workspace_reaper_preserves_active_and_preview_workspaces():
    stopped=[]
    def adapter(names):
        async def api(method,path,**kwargs):
            if method=='GET':return {'workspaces':[{'id':name,'latest_build':{'status':'running'}} for name in names]}
            stopped.append(path.split('/')[-2]);assert kwargs['json']=={'transition':'stop'}
        return SimpleNamespace(api=api,touched={},tasks={},active=set())
    coder=adapter(['busy','visible','idle']);coder.active={'busy'}
    developer=adapter(['human-active','human-idle']);developer.touched['human-active']=time.time()
    reaper=IdleWorkspaces(coder,developer,SimpleNamespace(active_workspaces=lambda:{'visible'}));reaper.started=0
    await reaper.reap()
    assert set(stopped)=={'idle','human-idle'}

@pytest.mark.asyncio
async def test_expired_preview_reclaims_server_and_forget_cached_url():
    from backend.previews import Previews
    from backend import preview
    closed=[]
    class Server:should_exit=False
    resource={'server':Server(),'task':asyncio.create_task(asyncio.sleep(0)),'process':None,'log':SimpleNamespace(close=lambda:closed.append(True))}
    p=Previews();p.resources[45555]=resource;p.app_ports[('coder','w')]='http://127.0.0.1:45555/'
    preview.targets[45555]={'expires':0,'workspace_id':'w'}
    await p.reap()
    assert not p.resources and not p.app_ports and 45555 not in preview.targets
    assert resource['server'].should_exit and closed==[True]

@pytest.mark.asyncio
async def test_project_capacity_pressure_stops_only_unused_owned_compute(monkeypatch):
    from backend.coder import CoderAgents,previews
    c=CoderAgents();c.max_running=4;c.active={'busy'};c.provisioning={'starting'}
    ws=[{'id':n,'template_id':'ai','latest_build':{'status':'running'}} for n in ['idle','busy','visible','starting']]
    stopped=[]
    async def api(method,path,**kwargs):
        if method=='GET':return {'workspaces':ws}
        assert kwargs['json']=={'transition':'stop'}
        wid=path.split('/')[-2];stopped.append(wid)
        next(w for w in ws if w['id']==wid)['latest_build']['status']='stopped'
    async def no_delay(_):pass
    monkeypatch.setattr(c,'api',api);monkeypatch.setattr(c,'settings',lambda:{'template_id':'ai'})
    monkeypatch.setattr(previews,'active_workspaces',lambda:{'visible'})
    monkeypatch.setattr('backend.coder.asyncio.sleep',no_delay)
    await c.ensure_capacity()
    assert stopped==['idle']

def test_shared_harness_defaults_skip_ori_wizard_and_preserve_user_profiles(tmp_path,monkeypatch):
    import importlib.util,json
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('harness_setup',Path(__file__).parents[1]/'sandbox/harness_setup.py')
    setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
    monkeypatch.setattr(setup.Path,'home',lambda:tmp_path)
    # The setup runs in Linux pods; validate settings without installing CLIs on the test host.
    monkeypatch.setattr(setup.platform,'machine',lambda:'aarch64')
    monkeypatch.setattr(setup.subprocess,'run',lambda *a,**k:None)
    settings=tmp_path/'.local/share/code-server/User/settings.json';settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'editor.fontSize':15,'terminal.integrated.profiles.linux':{'custom':{'path':'/bin/sh'}}}))
    setup.configure({'gui':True,'model':'test-model','reasoning':'xhigh','token':'test-capability','expires':123,'extension_files':{'package.json':'{}'}})
    assert json.loads((tmp_path/'.ori/config.json').read_text())['loginMode']=='environment'
    value=json.loads(settings.read_text())
    assert value['editor.fontSize']==15 and 'custom' in value['terminal.integrated.profiles.linux']
    assert value['lab.agent.openOnStartup'] is True
    assert 'test-capability' not in (tmp_path/'.pi/agent/models.json').read_text()
    model=json.loads((tmp_path/'.pi/agent/models.json').read_text())['providers']['lab']['models'][0]
    assert model['thinkingLevelMap']['xhigh']=='xhigh'
    assert (tmp_path/'.config/lab/token').stat().st_mode & 0o777 == 0o600
