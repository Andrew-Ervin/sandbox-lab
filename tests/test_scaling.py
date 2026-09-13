import asyncio,time
from types import SimpleNamespace
import pytest
from backend.scaling import WarmPolicy

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
    return SimpleNamespace(metadata=SimpleNamespace(name=name,labels={'lab/state':state},resource_version='1',deletion_timestamp=None),status=SimpleNamespace(phase=phase,container_statuses=[SimpleNamespace(ready=True)],conditions=[SimpleNamespace(type='Ready',status='True')]))

@pytest.mark.asyncio
async def test_expired_preview_reclaims_server_and_forget_cached_url():
    from backend.previews import Previews
    from backend import preview
    closed=[]
    class Server:should_exit=False
    resource={'server':Server(),'task':asyncio.create_task(asyncio.sleep(0)),'process':None,'log':SimpleNamespace(close=lambda:closed.append(True))}
    p=Previews();p.resources[45555]=resource;p.app_ports[('headless','w')]='http://127.0.0.1:45555/'
    preview.targets[45555]={'expires':0,'workspace_id':'w'}
    await p.reap()
    assert not p.resources and not p.app_ports and 45555 not in preview.targets
    assert resource['server'].should_exit and closed==[True]

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
