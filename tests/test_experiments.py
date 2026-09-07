import importlib,os,subprocess,sys
from pathlib import Path
import pytest


def test_disabled_experiment_never_needs_private_files(monkeypatch,tmp_path):
    import backend.experiments as module
    monkeypatch.setenv('LAB_ENABLE_MCP_EXPERIMENT','false')
    monkeypatch.setattr(module,'STATE',tmp_path)
    disabled=module.load_experiment()
    assert not disabled.enabled and not disabled.TOOLS and not disabled.NAMES
    assert disabled.prepare_agent_request({'prompt':'hello'})=={'prompt':'hello'}
    assert '/opt/lab/agent.py' in disabled.agent_wrapper()
    assert disabled.configure_gui('unused') is None
    disabled.install(None,None,None)


def test_explicit_missing_experiment_fails_with_actionable_error(monkeypatch,tmp_path):
    import backend.experiments as module
    monkeypatch.setattr(module,'STATE',tmp_path)
    monkeypatch.setenv('LAB_ENABLE_MCP_EXPERIMENT','true')
    with pytest.raises(RuntimeError,match='Disable it'):module.load_experiment()


def test_new_capabilities_have_no_request_allowance(monkeypatch):
    import base64,json
    from backend.capabilities import issue
    monkeypatch.setenv('LAB_TOKEN_SECRET','s'*32)
    result=issue('test-workspace')
    claims=json.loads(base64.urlsafe_b64decode(result['token'].split('.')[0]+'=='))
    assert 'calls' not in claims and claims['exp']-claims['iat']==3600
