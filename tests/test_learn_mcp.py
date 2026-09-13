import json
import tomllib
from unittest.mock import Mock
import pytest
from sandbox.learn_mcp import handle
from sandbox.harness_setup import configure_learn_mcp


def test_learn_bridge_rejects_unknown_tools_and_methods_before_network():
    client=Mock()
    for request in ({'method':'tools/call','params':{'name':'shell','arguments':{}}},
                    {'method':'resources/read','params':{'uri':'file:///etc/passwd'}}):
        with pytest.raises(ValueError):handle(client,{'jsonrpc':'2.0','id':1,**request})
    client.call.assert_not_called()


def test_learn_bridge_limits_discovery_and_does_not_forward_client_metadata():
    client=Mock(headers={})
    client.call.return_value={'protocolVersion':'2025-03-26'}
    handle(client,{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'clientInfo':{'private':'value'},'capabilities':{'roots':{}}}})
    assert client.call.call_args.args[1]['capabilities']=={}
    assert 'private' not in json.dumps(client.call.call_args.args)
    client.call.return_value={'tools':[{'name':'microsoft_docs_search'},{'name':'unapproved-new-tool'}]}
    assert handle(client,{'jsonrpc':'2.0','id':2,'method':'tools/list'})=={'tools':[{'name':'microsoft_docs_search'}]}


def test_native_mcp_setup_preserves_existing_configuration_and_is_idempotent(tmp_path):
    (tmp_path/'.codex').mkdir()
    (tmp_path/'.codex/config.toml').write_text('model = "user-choice"\n[mcp_servers.existing]\ncommand="existing"\n')
    (tmp_path/'.claude.json').write_text(json.dumps({'projects':{'example':{'hasTrustDialogAccepted':False}}}))
    configure_learn_mcp(tmp_path);configure_learn_mcp(tmp_path)
    codex=tomllib.loads((tmp_path/'.codex/config.toml').read_text())
    assert codex['model']=='user-choice'
    assert set(codex['mcp_servers'])=={'existing','microsoft-learn'}
    claude=json.loads((tmp_path/'.claude.json').read_text())
    assert claude['projects']['example']['hasTrustDialogAccepted'] is False
    assert claude['mcpServers']['microsoft-learn']['args']==['-I','/opt/lab/learn_mcp.py','--stdio']
