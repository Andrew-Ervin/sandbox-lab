import importlib.util
import json
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('download_tools',ROOT/'scripts/download_tools.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@pytest.mark.parametrize('system,machine,expected', [('Linux','x86_64',('linux','amd64')),('Linux','aarch64',('linux','arm64')),('Darwin','arm64',('darwin','arm64')),('Darwin','x86_64',('darwin','amd64'))])
def test_platform_uses_matching_pinned_downloads(system,machine,expected):
    assert m.target(system,machine)==expected
    lock=json.loads((ROOT/'scripts/tool-downloads.lock.json').read_text())
    assets=m.plan(*expected)
    for asset in assets.values():
        assert len(lock[asset]['sha256'])==64
        assert 'latest' not in lock[asset]['url']
    assert ('x64' if expected[1]=='amd64' else 'arm64') in assets['ori']
    assert expected[1] in assets['code-server']


def test_native_windows_requires_wsl():
    with pytest.raises(ValueError,match='WSL2'):m.target('Windows','AMD64')
