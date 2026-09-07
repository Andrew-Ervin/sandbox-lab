import base64,json,time
from types import SimpleNamespace
import pytest,yaml
from scripts import broker_credentials as module


def token(expires):
    return 'synthetic.'+base64.urlsafe_b64encode(json.dumps({'exp':expires}).encode()).decode().rstrip('=')+'.signature'


def test_renewal_keeps_only_scoped_identity_and_skips_valid_token(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(module,'STATE',tmp_path)
    source={'clusters':[],'users':[{'name':'operator','user':{'client-key-data':'private'}}],'contexts':[{'name':'local','context':{'user':'operator'}}]}
    (tmp_path/'kubeconfig').write_text(yaml.safe_dump(source))
    credential=token(time.time()+86400);commands=[]
    def run(command,**kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0,stdout=credential,stderr='')
    monkeypatch.setattr(module.subprocess,'run',run)
    assert module.renew()
    path=tmp_path/'broker-kubeconfig';result=yaml.safe_load(path.read_text())
    assert result['users']==[{'name':'broker','user':{'token':credential}}]
    assert result['contexts'][0]['context']=={'user':'broker','namespace':'lab-sandboxes'}
    assert path.stat().st_mode&0o777==0o600
    assert commands[0][-4:]==['create','token','broker','--duration=86400s']
    assert not module.renew() and len(commands)==1
    assert credential not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_quick_authentication_error_does_not_echo_headers(monkeypatch):
    from backend.compute import Compute
    from kubernetes.client.exceptions import ApiException
    runtime=Compute()
    def fail(*args,**kwargs):
        error=ApiException(status=401,reason='Unauthorized');error.body='private';error.headers={'secret':'private'};raise error
    monkeypatch.setattr(runtime,'api',lambda:SimpleNamespace(test=fail,api_client=SimpleNamespace(close=lambda:None)))
    with pytest.raises(RuntimeError,match='authenticate to Kubernetes') as exc:
        await runtime.call('test')
    assert 'private' not in str(exc.value)


def test_workspace_rotation_is_atomic_private_and_keeps_other_files(tmp_path):
    from sandbox.rotate_capability import rotate
    folder=tmp_path/'.config/lab';folder.mkdir(parents=True);(folder/'token').write_text('old')
    (folder/'other').write_text('preserve')
    result=rotate({'token':'new synthetic credential','expires':12345,'model':'test'},tmp_path)
    assert result=={'expires':12345} and (folder/'token').read_text()=='new synthetic credential'
    assert (folder/'token').stat().st_mode&0o777==0o600
    assert (folder/'other').read_text()=='preserve' and not list(folder.glob('.renew-*'))


@pytest.mark.asyncio
async def test_model_token_renewal_never_wakes_or_touches_idle_workspaces(monkeypatch):
    from backend.developer import DeveloperWorkspaces
    from unittest.mock import AsyncMock
    dev=DeveloperWorkspaces();dev.touched={'active':time.time(),'idle':0}
    rows=[{'id':name,'latest_build':{'status':status}} for name,status in [('active','running'),('idle','running'),('sleeping','stopped')]]
    dev.api=AsyncMock(return_value={'workspaces':rows});dev.activity=AsyncMock(return_value=0);dev.refresh_capability=AsyncMock()
    await dev.renew_active()
    dev.refresh_capability.assert_awaited_once_with('active')
    assert dev.touched['idle']==0
    assert all(c.args[0]=='GET' for c in dev.api.call_args_list)
