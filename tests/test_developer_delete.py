import asyncio
from unittest.mock import AsyncMock
import pytest
from backend.developer import DeveloperWorkspaces

@pytest.mark.asyncio
async def test_delete_uses_coder_and_cancels_setup():
    dev=DeveloperWorkspaces()
    dev.list=AsyncMock(return_value=[{'id':'owned','status':'running'}])
    dev.api=AsyncMock()
    task=asyncio.create_task(asyncio.sleep(100))
    dev.tasks['owned']=task
    dev.configured_until['owned']=123
    assert (await dev.delete('owned'))['status']=='deleting'
    dev.api.assert_awaited_once_with('POST','/api/v2/workspaces/owned/builds',json={'transition':'delete'})
    assert task.cancelled()
    assert 'owned' not in dev.configured_until

@pytest.mark.asyncio
async def test_delete_rejects_unknown_and_busy_workspaces():
    dev=DeveloperWorkspaces();dev.api=AsyncMock()
    dev.list=AsyncMock(return_value=[{'id':'owned','status':'starting'}])
    with pytest.raises(LookupError): await dev.delete('someone-else')
    with pytest.raises(ValueError): await dev.delete('owned')
    dev.api.assert_not_awaited()

@pytest.mark.asyncio
async def test_delete_in_progress_is_idempotent():
    dev=DeveloperWorkspaces();dev.api=AsyncMock()
    dev.list=AsyncMock(return_value=[{'id':'owned','status':'deleting'}])
    await dev.delete('owned')
    dev.api.assert_not_awaited()

@pytest.mark.asyncio
async def test_failed_build_stops_setup_wait_and_prepare_does_not_retry_twice():
    dev=DeveloperWorkspaces()
    dev.api=AsyncMock(return_value={'latest_build':{'status':'failed','resources':[]}})
    dev.configure('owned','project')
    with pytest.raises(RuntimeError,match='storage/compute quota'):
        await dev.prepare({'id':'owned','name':'project'})
    dev.api.assert_awaited_once()
    assert 'startup failed' in dev.setup_errors['owned']

@pytest.mark.asyncio
async def test_ready_configuration_is_reused():
    import time
    dev=DeveloperWorkspaces();dev.api=AsyncMock()
    dev.configured_until['owned']=time.time()+100
    await dev.prepare({'id':'owned','name':'project'})
    dev.api.assert_not_awaited()

@pytest.mark.asyncio
async def test_rejected_login_session_retries_once_not_recursively(tmp_path,monkeypatch):
    import json,httpx
    import backend.developer as module
    (tmp_path/'coder-admin.json').write_text(json.dumps({'email':'test@example.invalid','password':'synthetic'}))
    monkeypatch.setattr(module,'STATE',tmp_path)
    calls=[]
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200,json={'session_token':'test'}) if request.url.path.endswith('/login') else httpx.Response(401)
    real=httpx.AsyncClient
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(httpx.HTTPStatusError):await DeveloperWorkspaces().api('GET','/api/v2/users/me')
    assert len(calls)==4
