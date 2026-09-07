import importlib.util
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
