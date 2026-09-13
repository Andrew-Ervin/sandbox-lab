"""Install the existing human-only Pi/Ori harness through approved package routes."""
import json
import hashlib
import shlex
from .config import ROOT, STATE


async def configure(adapter, workspace):
    from .capabilities import issue
    from .workspace_models import refresh
    await refresh()
    record = adapter.runtime.record(workspace['id']); sid = record['sandbox_id']
    group = adapter.runtime.profile('developer')['group']
    learn=adapter.runtime.config.get('workspace_mcp_learn') is True
    if record.get('workspace_mcp_learn') is not learn:
        await adapter.runtime.transport.call('workspace_mcp_policy',group,sid)
        record['workspace_mcp_learn']=learn;adapter.runtime.save(record)
    if learn:
        await adapter.runtime.transport.write(group,sid,'/opt/lab/learn_mcp.py',(ROOT/'sandbox/learn_mcp.py').read_bytes(),'0644')
    ori = STATE/'bin/ori-linux-amd64'
    expected = json.loads((ROOT/'scripts/tool-downloads.lock.json').read_text())['ori-linux-x64']['sha256']
    if not ori.exists() or hashlib.sha256(ori.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Verified Linux AMD64 Ori is missing; run scripts/setup_azure_runtime.py --tools.')
    preinstalled = adapter.runtime.profile('developer').get('preinstalled_tools',False)
    pi = '/usr/local/bin/pi' if preinstalled else '/home/sandbox/.local/share/pi/node_modules/.bin/pi'
    ori_remote = '/usr/local/bin/ori' if preinstalled else '/opt/lab/bin/ori'
    check = "import hashlib; from pathlib import Path; p=Path('/opt/lab/bin/ori'); print(hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else '')"
    if not preinstalled and (await adapter.runtime.root_exec(record, 'python -I -c '+shlex.quote(check))).strip() != expected:
        await adapter.runtime.transport.write(group,sid,'/opt/lab/bin/ori',ori.read_bytes(),'0755')
    check = "import json; from pathlib import Path; p=Path('/home/sandbox/.local/share/pi/node_modules/@earendil-works/pi-coding-agent/package.json'); print(json.loads(p.read_text()).get('version') if p.is_file() else '')"
    if not preinstalled and (await adapter.runtime.root_exec(record, 'python -I -c '+shlex.quote(check))).strip() != '0.85.1':
        result = await adapter.execute(workspace,['npm','install','--prefix','/home/sandbox/.local/share/pi','--no-audit','--no-fund','@earendil-works/pi-coding-agent@0.85.1'],timeout=180,maximum=1000000)
        if result['exit_code']:
            folder = adapter.runtime.root/'diagnostics'; folder.mkdir(exist_ok=True, mode=0o700)
            path = folder/(workspace['id']+'-pi-install.json')
            path.write_text(json.dumps(result)); path.chmod(0o600)
            raise RuntimeError('Pi installation failed; private setup diagnostics were saved. The package policy was not changed.')
    # Ori discovers Pi on PATH even when the wrapper passes explicit Pi flags.
    await adapter.runtime.root_exec(record, "python -I -c \"from pathlib import Path; p=Path('/opt/lab/bin/pi'); p.unlink(missing_ok=True); p.symlink_to("+repr(pi)+")\"")
    # Curated extension assets arrive in the versioned root-owned runtime bundle.
    script = (ROOT/'sandbox/harness_setup.py').read_text()
    script = script.rsplit("\nif __name__", 1)[0]
    script = script.replace('/usr/local/bin/pi',pi).replace('/usr/local/bin/ori',ori_remote)
    package_setup = (ROOT/'sandbox/package_setup.py').read_text()
    templates = {str(p.relative_to(ROOT/'sandbox/ori-templates')):p.read_text() for p in (ROOT/'sandbox/ori-templates').rglob('*') if p.is_file() and not p.is_symlink()}
    extensions=json.loads((ROOT/'infra/editor-extensions.lock.json').read_text())['extensions']
    payload = {**issue(workspace['id']), 'gui':True, 'package_setup':package_setup, 'ori_templates':templates, 'editor_extensions':extensions,'microsoft_learn_mcp':learn}
    await adapter.invoke(workspace,script+'\nimport json,sys; print(json.dumps(configure(json.load(sys.stdin))))',payload,timeout=300)
    adapter.capability_until[workspace['id']] = payload['expires']
