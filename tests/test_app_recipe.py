import importlib.util
import json
from pathlib import Path


def test_vite_uses_preview_port_without_rewriting_other_commands(tmp_path,monkeypatch):
    monkeypatch.setenv('HOME',str(tmp_path))
    spec=importlib.util.spec_from_file_location('app_runtime_test',Path(__file__).parents[1]/'sandbox/app_runtime.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=tmp_path
    (tmp_path/'package.json').write_text(json.dumps({'scripts':{'dev':'vite --host 0.0.0.0','start':'node server.js'}}))
    _,argv=module.checked({'cwd':'.','command':['npm','run','dev']})
    assert argv[-5:]==['--host','0.0.0.0','--port','3000','--strictPort']
    _,argv=module.checked({'cwd':'.','command':['npm','run','start']})
    assert argv==['npm','run','start']
