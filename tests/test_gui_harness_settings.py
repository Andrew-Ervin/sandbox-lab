import json,tomllib
from sandbox.harness_setup import configure_native_settings

def test_native_settings_on_fresh_home_use_gateway_not_upstream_key(tmp_path):
    configure_native_settings(tmp_path,{'model':'test/model'})
    codex=tomllib.loads((tmp_path/'.codex/config.toml').read_text())
    assert codex['model']=='test/model'
    assert codex['model_providers']['lab']['base_url'].endswith(':8080/v1')
    assert codex['analytics']['enabled'] is False
    claude=json.loads((tmp_path/'.claude/settings.json').read_text())
    assert claude['env']['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC']=='1'
    assert 'OPENROUTER_API_KEY' not in claude['env']
    settings=json.loads((tmp_path/'.local/share/code-server/User/settings.json').read_text())
    assert settings['claudeCode.useTerminal'] is False
