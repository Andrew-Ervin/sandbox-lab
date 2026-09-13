import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.editor_profiles import EditorProfiles
from sandbox import editor_preferences as preferences


@pytest.mark.asyncio
async def test_old_workspace_changes_merge_without_overwriting_newer_preferences():
    control=SimpleNamespace(db=sqlite3.connect(':memory:'))
    profiles=EditorProfiles(control)
    first={'settings':{'editor.fontSize':14,'workbench.colorTheme':'Dark'},'layout':{},'extensions':[],'keybindings':[]}
    profiles.command=AsyncMock(return_value=first)
    a={'id':'a','owner':'alice','kind':'developer'};b={**a,'id':'b'}
    await profiles.capture(a);await profiles.restore(b)
    profiles.command.return_value={**first,'settings':{**first['settings'],'editor.fontSize':18}}
    await profiles.capture(a)
    profiles.command.return_value={**first,'settings':{**first['settings'],'workbench.colorTheme':'Light'}}
    await profiles.capture(b)
    assert profiles.get('alice')['profile']['settings']=={'editor.fontSize':18,'workbench.colorTheme':'Light'}
    assert profiles.get('bob')['profile'] is None


def test_portable_settings_never_copy_provider_credentials_or_security_controls(tmp_path,monkeypatch):
    monkeypatch.setattr(preferences,'USER',tmp_path)
    original={'editor.fontSize':14,'security.workspace.trust.enabled':True,'claudeCode.environmentVariables':['private']}
    (tmp_path/'settings.json').write_text(json.dumps(original))
    preferences.apply({'settings':{'editor.fontSize':20,'security.workspace.trust.enabled':False,'http.proxyAuthorization':'secret'}})
    result=json.loads((tmp_path/'settings.json').read_text())
    assert result=={**original,'editor.fontSize':20}
    exported=preferences.export()
    assert exported['settings']=={'editor.fontSize':20}


def test_settings_symlink_is_not_followed(tmp_path,monkeypatch):
    user=tmp_path/'User';user.mkdir();private=tmp_path/'private';private.write_text('{"editor.fontSize":99}')
    (user/'settings.json').symlink_to(private);monkeypatch.setattr(preferences,'USER',user)
    assert preferences.export()['settings']=={}
    with pytest.raises(ValueError):preferences.apply({'settings':{}})


def test_editor_jsonc_preserves_strings_comments_and_trailing_commas():
    assert preferences.parse_jsonc('{// personal choice\n"editor.fontSize":18, /* note */ "label":"https://host/a,b",}')=={'editor.fontSize':18,'label':'https://host/a,b'}

@pytest.mark.asyncio
async def test_open_syncs_only_same_owner_running_workspaces():
    a={'id':'a','owner':'alice','kind':'developer','state':'running'}
    records=[a,{**a,'id':'b'},{**a,'id':'c','state':'stopped'},{**a,'id':'d','owner':'bob'}]
    control=SimpleNamespace(db=sqlite3.connect(':memory:'),records=lambda:records,resizing=set())
    profiles=EditorProfiles(control);profiles.capture=AsyncMock();profiles.restore=AsyncMock()
    await profiles.for_open(a)
    profiles.capture.assert_awaited_once_with(records[1]);profiles.restore.assert_awaited_once_with(a)

def test_project_appearance_migrates_with_backup_without_moving_project_rules(tmp_path,monkeypatch):
    user=tmp_path/'User';user.mkdir();workspace=tmp_path/'settings.json'
    monkeypatch.setattr(preferences,'USER',user);monkeypatch.setattr(preferences,'WORKSPACE',workspace)
    original={'workbench.colorTheme':'Dark','editor.tabSize':4}
    workspace.write_text(json.dumps(original))
    profile=preferences.export()
    assert profile['settings']=={'workbench.colorTheme':'Dark'}
    preferences.apply(profile)
    assert json.loads(workspace.read_text())=={'editor.tabSize':4}
    assert json.loads(workspace.with_suffix('.json.before-account-profile').read_text())==original


@pytest.mark.asyncio
async def test_unhealthy_peer_does_not_block_target_open():
    from unittest.mock import Mock
    a={'id':'a','owner':'alice','kind':'developer','state':'running'}
    control=SimpleNamespace(db=sqlite3.connect(':memory:'),records=lambda:[a,{**a,'id':'b'}],resizing=set(),telemetry=SimpleNamespace(event=Mock()))
    profiles=EditorProfiles(control);profiles.capture=AsyncMock(side_effect=RuntimeError('offline'));profiles.restore=AsyncMock()
    await profiles.for_open(a)
    profiles.restore.assert_awaited_once_with(a)
    control.telemetry.event.assert_called_once()

@pytest.mark.asyncio
async def test_open_uses_only_most_recent_peer_and_bounds_wait(monkeypatch):
    from unittest.mock import Mock
    import asyncio
    a={'id':'a','owner':'alice','kind':'developer','state':'running'}
    records=[a,{**a,'id':'b','last_activity_at':1},{**a,'id':'c','last_activity_at':2}]
    control=SimpleNamespace(db=sqlite3.connect(':memory:'),records=lambda:records,resizing=set(),telemetry=SimpleNamespace(event=Mock()))
    profiles=EditorProfiles(control);profiles.capture=AsyncMock();profiles.restore=AsyncMock()
    async def timeout(coro,timeout):
        assert timeout==2
        await coro
        raise asyncio.TimeoutError()
    monkeypatch.setattr('backend.editor_profiles.asyncio.wait_for',timeout)
    await profiles.for_open(a)
    profiles.capture.assert_awaited_once_with(records[2])
    profiles.restore.assert_awaited_once_with(a)
