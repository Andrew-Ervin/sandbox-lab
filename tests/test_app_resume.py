import asyncio,importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from backend.apps import AppLifecycle

@pytest.mark.asyncio
async def test_click_resume_owns_workspace_and_serializes_launches(monkeypatch):
    runtime=AppLifecycle();inside=0;peak=0
    class Store:
        async def load_thread(self,thread,context):return SimpleNamespace(id=thread,metadata={'workspace_id':'owned'})
        def project_for_thread(self,*args):return None
    class Azure:
        provisioning=set();touched={}
        async def workspace(self,*args):return {'id':'owned','name':'ai-demo'}
        def settings(self):return {'token':'bounded-test'}
    class Previews:
        async def app(self,*args,**kwargs):return 'http://127.0.0.1:5000/'
    headless=Azure()
    async def launch(ws,*args):
        nonlocal inside,peak
        assert ws['id'] in headless.provisioning
        inside+=1;peak=max(peak,inside);await asyncio.sleep(.01);inside-=1
    monkeypatch.setattr(runtime,'launch',launch)
    run={'workspace_id':'owned','thread_id':'thread'}
    urls=await asyncio.gather(*[runtime.ai(run,Store(),'alice',headless,Previews()) for _ in range(2)])
    assert peak==1 and urls==['http://127.0.0.1:5000/']*2 and not headless.provisioning
    with pytest.raises(ValueError):await runtime.ai({**run,'workspace_id':'foreign'},Store(),'alice',headless,Previews())

def test_app_recipe_confines_cwd_and_discovers_saved_static_build(tmp_path,monkeypatch):
    # Avoid module-level home writes during import; this script normally runs in a sandbox.
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    spec=importlib.util.spec_from_file_location('app_runtime',Path(__file__).parents[1]/'sandbox/app_runtime.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    root=tmp_path/'project';root.mkdir();m.ROOT=root;m.RECIPE=root/'.lab/app.json'
    (root/'site/dist').mkdir(parents=True);(root/'site/dist/index.html').write_text('<h1>Site</h1>')
    recipe=m.discover();assert recipe['cwd']=='site' and recipe['command'][-1]=='dist'
    with pytest.raises(ValueError):m.checked({'cwd':'..','command':['sh']})
    with pytest.raises(ValueError):m.checked({'cwd':'.','command':'shell command'})


def test_developer_preview_uses_the_copied_source_folder(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    spec=importlib.util.spec_from_file_location('app_runtime_copy',Path(__file__).parents[1]/'sandbox/app_runtime.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    root=tmp_path/'project';root.mkdir();m.ROOT=root
    folder=root/'.lab/imports'/('transfer_'+'a'*32);folder.mkdir(parents=True)
    (folder/'main.go').write_text('package main')
    with pytest.raises(ValueError):m.select_source('../outside')
    m.select_source(str(folder.relative_to(root)))
    assert m.ROOT==folder and m.discover()=={'cwd':'.','command':['go','run','main.go']}


@pytest.mark.asyncio
async def test_renamed_workstation_resumes_by_identity_without_creating_another(monkeypatch):
    from unittest.mock import AsyncMock, Mock
    workspace={'id':'existing','name':'My Renamed Workstation','status':'stopped'}
    developer=SimpleNamespace(lookup=Mock(return_value=workspace),prepare=AsyncMock(),ide=AsyncMock(return_value='http://127.0.0.1:5555/'),touched={})
    result=await AppLifecycle().human('existing',developer,None,ide=True)
    developer.prepare.assert_awaited_once_with(workspace,editor=True)
    assert result=='http://127.0.0.1:5555/'


@pytest.mark.asyncio
async def test_preview_reuse_rejects_a_different_project_source(monkeypatch):
    from backend.previews import Previews
    from unittest.mock import AsyncMock
    previews=Previews()
    previews.azure_app=AsyncMock(return_value='http://127.0.0.1:5555/')
    await previews.app({'id':'existing'},source_path='.lab/imports/transfer_'+'a'*32)
    previews.azure_app.reset_mock()
    assert await previews.ready_app('existing','.lab/imports/transfer_'+'b'*32) is None
    assert await previews.ready_app('existing',None) is None
    previews.azure_app.assert_not_awaited()


@pytest.mark.asyncio
async def test_app_open_does_not_wait_for_editor_preferences_or_harness():
    from unittest.mock import AsyncMock, Mock
    ws={'id':'owned','name':'Example'}
    developer=SimpleNamespace(lookup=Mock(return_value=ws),prepare=AsyncMock(),touched={},token='')
    previews=SimpleNamespace(ready_app=AsyncMock(return_value=None),app=AsyncMock(return_value='preview'))
    lifecycle=AppLifecycle();lifecycle.launch=AsyncMock()
    assert await lifecycle.human('owned',developer,previews,ide=False)=='preview'
    developer.prepare.assert_awaited_once_with(ws,editor=False)


def test_local_workspace_lookup_enforces_owner_and_kind(tmp_path):
    from backend.azure_adapters import AzureDeveloper
    from backend.azure_runtime import AzureRuntime
    from backend.identity import current_owner
    adapter=object.__new__(AzureDeveloper)
    adapter.runtime=AzureRuntime(tmp_path,{});adapter.harness={};adapter.setup_errors={}
    record={'id':'owned','owner':'alice','name':'Example','kind':'developer','state':'running','created_at':1,'updated_at':1}
    adapter.runtime.save(record)
    token=current_owner.set('alice')
    try:
        assert adapter.lookup('owned')['id']=='owned'
        for changes in ({'owner':'bob'},{'kind':'headless'},{'warm':True},{'state':'deleted'}):
            adapter.runtime.save({**record,**changes})
            with pytest.raises(ValueError,match='Workspace not found'):adapter.lookup('owned')
    finally:current_owner.reset(token)
