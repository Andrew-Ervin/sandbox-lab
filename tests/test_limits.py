import json,os,subprocess,sys
import pytest
from backend.limits import validate,script_with_limits
from backend.workspace_links import checked_files
from backend.compute import pod_manifest

def test_default_limits_are_consistent():validate()

def test_limits_reject_invalid_audio_budget(monkeypatch):
    monkeypatch.setenv('DICTATION_MAX_BYTES','1')
    with pytest.raises(ValueError,match='WAV'):validate()

def test_operator_credentials_are_never_forwarded_to_generated_code(monkeypatch):
    monkeypatch.setenv('PRIVATE_SECRET','do-not-copy')
    monkeypatch.setenv('SYNC_MAX_FILE_BYTES','7')
    code=script_with_limits("import json; print(json.dumps({'limit':os.getenv('SYNC_MAX_FILE_BYTES'),'secret':os.getenv('PRIVATE_SECRET')}))")
    output=subprocess.check_output([sys.executable,'-I','-c',code],env={'PATH':os.environ['PATH']})
    assert json.loads(output)=={'limit':'7','secret':None}
    import base64
    with pytest.raises(ValueError,match='sync limit'):checked_files({'files':[{'path':'a.py','data':base64.b64encode(b'12345678').decode()}]})
