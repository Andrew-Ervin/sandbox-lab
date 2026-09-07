from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.coder import CoderAgents

@pytest.mark.asyncio
async def test_recover_created_workspace_before_claiming_another():
    c=CoderAgents();c.settings=lambda:{'template_id':'t','organization_id':'o'}
    thread=SimpleNamespace(id='thr_1234567890abcdef',metadata={})
    w={'id':'existing','name':'ai-1234567890abcdef','template_id':'t','latest_build':{'status':'running'}}
    c.api=AsyncMock(side_effect=[{'workspaces':[w]},w]);c.reserve.claim=AsyncMock()
    store=SimpleNamespace(save_thread=AsyncMock(),ensure_project=lambda thread,owner:thread.metadata.setdefault('project_id','prj_1234567890abcdef'))
    assert await c.allocate(thread,store,{'owner':'test'})=='existing'
    assert thread.metadata['coder_workspace_id']=='existing'
    c.reserve.claim.assert_not_called()
    assert all(call.args[0]=='GET' for call in c.api.call_args_list)

@pytest.mark.asyncio
async def test_failed_build_reports_storage_quota():
    c=CoderAgents();c.allocate=AsyncMock(return_value='w')
    c.api=AsyncMock(side_effect=[{'latest_build':{'id':'b','status':'failed','job':{'error':'terraform apply failed'}}},[{'output':'Error: exceeded quota: capacity, persistentvolumeclaims=10'}]])
    with pytest.raises(RuntimeError,match='exceeded quota'):
        await c.workspace(None,None,None)
    assert 'w' not in c.provisioning
