import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def test_npm_restore_uses_lockfile_and_repeats_only_after_changes(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('runtime',Path('sandbox/app_runtime.py'))
    mod=importlib.util.module_from_spec(spec)
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    spec.loader.exec_module(mod)
    root=tmp_path/'source';root.mkdir();(root/'package.json').write_text('{}');(root/'package-lock.json').write_text('{}')
    calls=[]
    def launch(argv,**kwargs):
        calls.append(argv);(root/'node_modules').mkdir(exist_ok=True)
        return SimpleNamespace(wait=lambda timeout:0)
    monkeypatch.setattr(mod.subprocess,'Popen',launch)
    mod.restore_packages(root,['npm','run','dev'],{})
    mod.restore_packages(root,['npm','run','dev'],{})
    assert calls==[['npm','ci','--no-audit','--no-fund']]
    (root/'package-lock.json').write_text('{"changed":true}')
    mod.restore_packages(root,['npm','run','dev'],{})
    assert len(calls)==2


def test_azure_lock_migration_preserves_versions_integrity_and_original(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('runtime',Path('sandbox/app_runtime.py'))
    mod=importlib.util.module_from_spec(spec)
    monkeypatch.setattr(Path,'home',lambda:tmp_path);spec.loader.exec_module(mod)
    old='http://package-proxy.lab-control.svc.cluster.local:3128/artifact/'+'a'*64
    entries={'node_modules/@scope/pkg':{'version':'1.2.3','integrity':'sha512-original','resolved':old},
             'node_modules/other':{'version':'4.5.6','resolved':'https://example.com/custom.tgz'}}
    lock=tmp_path/'package-lock.json';original=json.dumps({'packages':entries}).encode();lock.write_bytes(original)
    mod.normalize_legacy_lock(lock)
    migrated=json.loads(lock.read_text())['packages']
    assert migrated['node_modules/@scope/pkg']=={**entries['node_modules/@scope/pkg'],'resolved':'https://registry.npmjs.org/@scope/pkg/-/pkg-1.2.3.tgz'}
    assert migrated['node_modules/other']==entries['node_modules/other']
    backups=list(mod.STATE.glob('*.before-azure.json'))
    assert len(backups)==1 and backups[0].read_bytes()==original
    mod.normalize_legacy_lock(lock)
    assert len(list(mod.STATE.glob('*.before-azure.json')))==1


def test_azure_lock_migration_rejects_missing_integrity(tmp_path,monkeypatch):
    import pytest
    spec=importlib.util.spec_from_file_location('runtime',Path('sandbox/app_runtime.py'))
    mod=importlib.util.module_from_spec(spec)
    monkeypatch.setattr(Path,'home',lambda:tmp_path);spec.loader.exec_module(mod)
    lock=tmp_path/'package-lock.json'
    original=json.dumps({'packages':{'node_modules/pkg':{'version':'1.0.0','resolved':'http://package-proxy.lab-control.svc.cluster.local:3128/artifact/'+'b'*64}}})
    lock.write_text(original)
    with pytest.raises(ValueError,match='safely'):mod.normalize_legacy_lock(lock)
    assert lock.read_text()==original


def test_wrapped_vite_uses_preview_port(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('runtime',Path('sandbox/app_runtime.py'))
    mod=importlib.util.module_from_spec(spec)
    monkeypatch.setattr(Path,'home',lambda:tmp_path);spec.loader.exec_module(mod)
    mod.ROOT=tmp_path
    (tmp_path/'package.json').write_text(json.dumps({'scripts':{'dev':'env -u ELECTRON_RUN_AS_NODE -u NODE_ENV taskset -c 0 vite --host 0.0.0.0 --force'}}))
    cwd,command=mod.checked({'cwd':'.','command':['npm','run','dev']})
    assert command[-5:]==['--host','0.0.0.0','--port','3000','--strictPort']
    assert not mod.vite_script('env NODE_ENV=production vite build')
    assert not mod.vite_script('echo vite')
