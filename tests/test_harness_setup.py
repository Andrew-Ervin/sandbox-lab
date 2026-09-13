import json
import subprocess
from pathlib import Path

from sandbox.harness_setup import configure_gui_harnesses
from scripts.patch_pi_webview import patch


def test_ori_adapters_preserve_harness_options_and_use_scoped_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr('sandbox.harness_setup.platform.machine', lambda: 'x86_64')
    packages = tmp_path / '.local/share/lab-harnesses/node_modules'
    (packages / '@openai/codex-linux-x64').mkdir(parents=True)
    real = packages / '.bin'
    real.mkdir()
    for name in ('codex', 'claude'):
        executable = real / name
        executable.write_text('#!/usr/bin/env python3\nimport json,os,sys\nprint(json.dumps({"args":sys.argv[1:],"base":os.environ.get("ANTHROPIC_BASE_URL")}))\n')
        executable.chmod(0o755)
    launchers = tmp_path / '.local/bin'
    launchers.mkdir(parents=True)
    configure_gui_harnesses(tmp_path, launchers, {'model':'test/model'}, '#!/bin/sh\n')
    adapters = tmp_path / '.config/lab/harness-adapters'
    r = subprocess.run([str(adapters/'codex'), '-c', 'model_providers.openrouter.base_url="https://openrouter.ai/api/v1"', '--sandbox', 'workspace-write'], capture_output=True, text=True, check=True)
    assert json.loads(r.stdout)['args'] == ['-c', 'model_providers.openrouter.base_url="http://127.0.0.1:8080/v1"', '--sandbox', 'workspace-write']
    r = subprocess.run([str(adapters/'claude'), '--settings', json.dumps({'permissions':{'defaultMode':'default'}})], capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)
    settings = json.loads(data['args'][1])
    assert data['base'] == settings['env']['ANTHROPIC_BASE_URL'] == 'http://127.0.0.1:8080'
    assert settings['permissions'] == {'defaultMode':'default'}
    assert 'ori codex' in (launchers/'codex-lab').read_text()
    assert 'ori claude' in (launchers/'claude-lab').read_text()
    for name, target in [('pi','ori-lab'),('codex','codex-lab'),('claude','claude-lab')]:
        assert target in (launchers/name).read_text()


def test_webview_assets_preserve_nonce_and_escape_closing_tags(tmp_path):
    media = tmp_path / 'media'
    media.mkdir()
    for name, content in {'style.css':'body{} </style><script>bad()</script>', 'vendor.js':'console.log("</script>")', 'main.js':'console.log("hello")'}.items():
        (media/name).write_text(content)
    fixture = '''const fs=require("fs"),path=require("path");
const view={extensionUri:{fsPath:ROOT},html(){let s="testnonce";return `<link rel="stylesheet" href="${t}"><script nonce="${s}" src="${r}"></script><script nonce="${s}" src="${n}"></script>`}};
console.log(view.html());'''.replace('ROOT', json.dumps(str(tmp_path)))
    result = patch(fixture)
    assert patch(result) == result
    html = subprocess.run(['node','-e',result],capture_output=True,text=True,check=True).stdout
    assert html.count('<script nonce="testnonce">') == 2
    assert '<\\/script>' in html and '<\\/style>' in html
    assert 'src=' not in html and 'href=' not in html
