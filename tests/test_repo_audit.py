import importlib.util
import subprocess
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('repo_audit',Path(__file__).parents[1]/'scripts/repo_audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

@pytest.mark.parametrize('name',['.local/state.json','.env','.env.production','docs/VERIFICATION.md','infra/prod.tfstate','user-apps/app.html','kubeconfig','nested/secret.pem'])
def test_private_paths_are_blocked(name):
    assert audit.findings(name,b'harmless')

def test_secrets_do_not_appear_in_diagnostics():
    credential=('sk-or-v1-'+'a'*64).encode()
    result=audit.findings('config.py',credential)
    assert result and credential.decode() not in repr(result)
    assert audit.findings('config.py',b'local-private-value',[b'local-private-value'])
    assert not audit.findings('.env.example',b'OPENROUTER_API_KEY=\n')

def test_staged_audit_reads_index_and_catches_force_added_private_files(tmp_path):
    def git(*args):return subprocess.run(['git','-C',str(tmp_path),*args],check=True,capture_output=True)
    git('init')
    (tmp_path/'.gitignore').write_text('.env\n')
    (tmp_path/'.env').write_text('OPENROUTER_API_KEY=fixture-private-credential')
    git('add','-f','.env')
    (tmp_path/'.env').write_text('')  # working copy cannot conceal staged content
    files,issues=audit.audit(tmp_path,staged=True)
    assert files[0][1] == b'OPENROUTER_API_KEY=fixture-private-credential'
    assert any(reason=='private/generated path' for _,_,reason in issues)

def test_temporary_local_tool_wiring_cannot_be_published():
    for source in (b'import live_bridge\n',b'    from .chat import live_bridge\n',b'    from gui_setup import install\n'):
        assert any('temporary local experiment' in issue[2] for issue in audit.findings('backend/demo.py',source))
