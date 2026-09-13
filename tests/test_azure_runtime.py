import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.azure_budget import AzureBudget
from backend.azure_runtime import AzureRuntime
from backend.azure_transport import AzureError
from backend.runtime_provider import provider


def test_budget_is_cumulative_durable_and_does_not_reset_with_month(tmp_path):
    path=tmp_path/'budget.sqlite';budget=AzureBudget(path)
    first=budget.reserve('compute',60);budget.finish(first)
    other=AzureBudget(path)
    assert other.status()['estimated_and_reserved_usd']==60
    with pytest.raises(RuntimeError,match='budget'):other.reserve('compute',41)
    assert other.status()['available_usd']==40


def test_uncertain_operation_and_bill_keep_reservations(tmp_path):
    budget=AzureBudget(tmp_path/'budget.sqlite')
    ident=budget.reserve('compute',10)
    budget.refresh_billed(70)
    assert budget.status()['committed_usd']==130
    budget.finish(ident,2)
    assert budget.status()['committed_usd']==120
    budget.finish(ident,0)  # idempotent completion cannot refund again
    assert budget.status()['estimated_and_reserved_usd']==2
    budget.refresh_billed(1)
    assert budget.status()['billed_usd']==70


@pytest.mark.parametrize('amount',[0,-1,float('inf'),float('nan')])
def test_invalid_reservations_rejected(tmp_path,amount):
    budget=AzureBudget(tmp_path/'budget.sqlite')
    with pytest.raises(ValueError):budget.reserve('compute',amount)


class FakeTransport:
    def __init__(self):self.calls=[];self.remote=[];self.fail_create=False;self.fail_stop=False
    async def call(self,action,group,sandbox_id=None,args=None,**kwargs):
        self.calls.append((action,group,sandbox_id,args))
        if action=='list':return list(self.remote)
        if action=='create':
            item={'id':'remote-1','state':'Running','labels':args['labels']};self.remote.append(item)
            if self.fail_create:raise AzureError('create',504)
            return item
        if action=='get':return next(s for s in self.remote if s['id']==sandbox_id)
        if action=='resume':self.remote[0]['state']='Running';return self.remote[0]
        if action in ('stop','delete'):
            if self.fail_stop:raise AzureError(action,503)
            if action=='delete':self.remote=[]
            else:self.remote[0]['state']='Stopped'
            return {}
        raise AssertionError(action)


@pytest.fixture
def control(tmp_path):
    transport=FakeTransport()
    value=AzureRuntime(tmp_path,{'subscription_id':'s','resource_group':'rg','region':'eastus2'},transport)
    value.bootstrap=AsyncMock();value.ensure_services=AsyncMock()
    return value


@pytest.mark.asyncio
async def test_reads_and_persistent_gate_allocate_nothing(control):
    assert await control.list('headless')==[]
    with pytest.raises(RuntimeError,match='storage'):await control.create('headless','project')
    assert [c[0] for c in control.transport.calls]==['list']
    assert control.records()==[]


@pytest.mark.asyncio
async def test_create_timeout_reconciles_same_cloud_label_without_duplicate(control):
    control.transport.fail_create=True
    with pytest.raises(AzureError):await control.create('quick','one',disposable=True)
    assert len(control.records())==1
    control.transport.fail_create=False
    result=await control.create('quick','one',disposable=True)
    assert result['id']==control.records()[0]['id']
    assert [c[0] for c in control.transport.calls].count('create')==1
    assert control.budget.status()['estimated_and_reserved_usd']>0


@pytest.mark.asyncio
async def test_missing_create_result_does_not_blindly_resubmit(control):
    control.transport.fail_create=True
    with pytest.raises(AzureError):await control.create('quick','one',disposable=True)
    control.transport.remote=[]
    with pytest.raises(RuntimeError,match='unconfirmed'):await control.create('quick','one',disposable=True)
    assert [c[0] for c in control.transport.calls].count('create')==1


@pytest.mark.asyncio
async def test_failed_stop_keeps_remote_mapping_and_cost_reservation(control):
    ws=await control.create('quick','one',disposable=True)
    before=control.budget.status()['estimated_and_reserved_usd']
    control.transport.fail_stop=True
    with pytest.raises(AzureError):await control.stop(ws['id'],delete=True)
    assert control.record(ws['id'])['sandbox_id']=='remote-1'
    assert control.budget.status()['estimated_and_reserved_usd']==before
    control.transport.fail_stop=False
    await control.stop(ws['id'],delete=True)
    assert control.record(ws['id'])['state']=='deleted'


@pytest.mark.asyncio
async def test_other_project_not_deleted_to_make_capacity(control):
    await control.create('quick','one',disposable=True)
    with pytest.raises(RuntimeError,match='quota reached'):await control.create('quick','two',disposable=True)
    assert 'delete' not in [c[0] for c in control.transport.calls]


@pytest.mark.asyncio
async def test_expired_or_stopped_execution_never_autoresumes(control):
    ws=await control.create('quick','one',disposable=True)
    record=control.record(ws['id']);record['state']='stopped';control.save(record)
    with pytest.raises(RuntimeError,match='lease'):await control.execute(ws['id'],['echo','unsafe'])
    assert 'exec' not in [c[0] for c in control.transport.calls]


def test_legacy_ids_not_overwritten_on_read(control):
    with pytest.raises(RuntimeError,match='mapping is unavailable'):control.record('legacy')
    assert control.records()==[]


@pytest.mark.asyncio
async def test_idle_stop_ignores_startup_active_command_and_recent_activity(control):
    ws=await control.create('quick','idle-test',disposable=True)
    record=control.record(ws['id']);record['last_activity_at']=time.time()-1000
    record['state']='starting';control.save(record)
    assert not control.is_idle(record)
    record['state']='running';control.save(record)
    control.active_commands[record['id']]=1
    assert not control.is_idle(record)
    control.active_commands.clear()
    assert control.is_idle(record)
    # An idle decision made before acquiring the lifecycle lock is stale once
    # the user has started work. Recheck inside stop before any cloud mutation.
    record['last_activity_at']=time.time();control.save(record)
    await control.stop(record['id'],only_if_idle=True)
    assert not any(call[0]=='stop' for call in control.transport.calls)
    assert control.record(record['id'])['state']=='running'


@pytest.mark.asyncio
async def test_background_sync_protects_execution_without_extending_idle(control):
    from backend.activity import background_activity
    ws=await control.create('quick','sync-test',disposable=True)
    record=control.record(ws['id']);record['last_activity_at']=time.time()-1000;control.save(record)
    async def execute(*args,**kwargs):
        assert control.active_commands[ws['id']]==1
        assert not control.is_idle(control.record(ws['id']))
        return {'exit_code':0}
    control._execute=execute
    token=background_activity.set(True)
    try:await control.execute(ws['id'],['python','source-sync.py'])
    finally:background_activity.reset(token)
    assert control.record(ws['id'])['last_activity_at']==record['last_activity_at']
    assert control.is_idle(control.record(ws['id']))
    control.activities['quick']={ws['id']:time.time()}
    assert not control.is_idle(control.record(ws['id']))


def test_ide_relative_redirect_stays_on_its_isolated_origin():
    from backend.preview import ide_redirect
    assert ide_redirect('./?folder=/home/sandbox/project','',45000)=='/?folder=/home/sandbox/project'
    assert ide_redirect('../asset','base/editor',45000)=='/asset'
    for location in ['//127.0.0.1:3000/','http://127.0.0.1:3000/','https://example.com/','javascript:alert(1)','/\\evil','\n//evil']:
        assert ide_redirect(location,'',45000) is None


@pytest.mark.asyncio
async def test_more_retained_capacity_does_not_allow_more_active_compute(control):
    control.config['profiles'] = {'headless': {'retained_limit': 2}}
    control.transport.remote = [{'id': 'other-project', 'state': 'Running', 'labels': {}}]
    task=asyncio.create_task(control.create('headless', 'new-project', disposable=True))
    await asyncio.sleep(.05)
    assert not task.done() and control.queued['headless']==1
    assert not any(c[0] in ('create', 'delete', 'stop') for c in control.transport.calls)
    control.transport.remote[0]['state'] = 'Stopped'
    workspace = await asyncio.wait_for(task,2)
    assert workspace['latest_build']['status'] == 'running'
    assert control.transport.remote[0]['id'] == 'other-project'


def test_runtime_has_one_provider(monkeypatch):
    monkeypatch.setenv('SANDBOX_PROVIDER','other')
    assert provider()=='azure'


@pytest.mark.asyncio
async def test_project_files_use_provider_transport_without_ssh():
    from backend.projects import ProjectFiles
    adapter=SimpleNamespace(provider='azure',invoke=AsyncMock(return_value='{"entries":[]}'))
    browser=ProjectFiles(None,adapter)
    assert await browser.read({'id':'workspace'},'list')=={'entries':[]}
    adapter.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_bridge_rejects_missing_credentials_foreign_ports_and_expired_lease():
    from sandbox.azure_bridge import Bridge
    connection=SimpleNamespace(respond=lambda code,message:(code,message))
    bridge=Bridge({'token':'private','deadline':time.time()+60})
    request=SimpleNamespace(headers={},path='/tcp/3000')
    assert (await bridge.authenticate(connection,request))[0]==401
    request.headers={'Authorization':'Bearer private'};request.path='/tcp/8080'
    assert (await bridge.authenticate(connection,request))[0]==404
    request.path='/tcp/13337'
    assert (await bridge.authenticate(connection,request))[0]==404
    request.path='/tcp/3000';assert await bridge.authenticate(connection,request) is None
    bridge.deadline=0
    assert (await bridge.authenticate(connection,request))[0]==410

@pytest.mark.asyncio
async def test_clean_warm_sandbox_is_claimed_once_and_keeps_logical_identity(control):
    control.config['profiles']={'quick':{'retained_limit':3,'active_limit':3}}
    ws=await control.create('quick','standby',warm=True,disposable=True)
    async with control.lock:
        first=control.warm.claim('quick','first')
        second=control.warm.claim('quick','second')
    assert first['id']==ws['id'] and second is None
    assert control.record(ws['id'])['name']=='first'
    assert control.db.execute('SELECT name FROM workspaces WHERE id=?',(ws['id'],)).fetchone()[0]=='first'
    assert not control.record(ws['id'])['warm']
    assert control.record(ws['id'])['disposable']


@pytest.mark.asyncio
async def test_waiting_admission_is_cancelled_by_stop_all(control):
    control.config['profiles']={'quick':{'retained_limit':3,'active_limit':1}}
    await control.create('quick','first')
    queued=asyncio.create_task(control.create('quick','second'))
    await asyncio.sleep(.05)
    assert not queued.done()
    control.warm.pause()
    with pytest.raises(RuntimeError,match='cancelled'):await asyncio.wait_for(queued,2)
    assert control.queued['quick']==0
    assert len(control.transport.remote)==1


@pytest.mark.asyncio
async def test_hourly_cost_guard_queues_before_new_allocation(control):
    control.config['max_hourly_compute_usd']=.10
    task=asyncio.create_task(control.create('quick','limited'))
    await asyncio.sleep(.05)
    assert not any(c[0]=='create' for c in control.transport.calls)
    control.warm.pause()
    with pytest.raises(RuntimeError,match='cancelled'):await asyncio.wait_for(task,2)


def test_warm_window_is_ten_minutes_and_explicit_stop_clears_it(control,monkeypatch):
    now=[1000.]
    monkeypatch.setattr('backend.warm_pool.time.time',lambda:now[0])
    assert control.warm.status('quick')['target']==0
    control.warm.demand('quick');assert control.warm.status('quick')['target']==1
    now[0]=1601;assert control.warm.status('quick')['target']==0
    control.warm.demand('quick');control.warm.pause()
    assert control.warm.status('quick')['target']==0


@pytest.mark.asyncio
async def test_queued_warm_role_does_not_block_other_roles(control):
    began=[];gate=asyncio.Event()
    async def create(kind,*args,**kwargs):
        began.append(kind)
        await gate.wait()
    control.create=create
    for kind in ('quick','headless','developer'):control.warm.demand(kind)
    task=asyncio.create_task(control.warm.maintain())
    await asyncio.sleep(.02)
    assert set(began)=={'quick','headless','developer'}
    task.cancel();await asyncio.gather(task,return_exceptions=True)
    assert all(t.done() for t in control.warm.tasks.values())
