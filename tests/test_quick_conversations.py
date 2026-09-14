import asyncio,json
from weakref import WeakValueDictionary
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock
import pytest
from backend.azure_adapters import AzureQuick
from backend.identity import current_owner

@pytest.mark.asyncio
async def test_quick_reuses_owner_conversation_and_retains_successful_vm(tmp_path,monkeypatch):
    from backend import checkpoints
    from backend import files
    monkeypatch.setattr(checkpoints,'load',lambda tid:[])
    monkeypatch.setattr(checkpoints,'directory',lambda tid:tmp_path)
    monkeypatch.setattr(files,'inputs',lambda *args:[])
    records={};created=[]
    async def create(kind,name,**kw):
        created.append((name,kw['owner']))
        records.setdefault(name,{'id':name,'name':name})
        return records[name]
    rt=SimpleNamespace(create=create,record=lambda wid:records[wid],save=Mock(),touch=Mock(),stop=AsyncMock(),
        storage=SimpleNamespace(enabled=False),execute=AsyncMock(return_value={'exit_code':0,'stdout':json.dumps({'stdout':'ok'})}))
    q=object.__new__(AzureQuick);q.runtime=rt;q.slots=asyncio.Semaphore(10);q.thread_locks=WeakValueDictionary();q.queued=q.executing=0
    store=SimpleNamespace(save_run=Mock())
    token=current_owner.set('alice')
    try:
        for tid in ['a','a','b']:await q.quick('print(1)',{'id':'r','thread_id':tid},store)
        current_owner.set('bob');await q.quick('print(1)',{'id':'r','thread_id':'a'},store)
    finally:current_owner.reset(token)
    assert created[0]==created[1] and created[0]!=created[2] and created[0]!=created[3]
    rt.stop.assert_not_awaited()
    assert q.executing==q.queued==0
    assert len(q.thread_locks)==0

@pytest.mark.asyncio
async def test_quick_execution_requires_owner():
    q=object.__new__(AzureQuick)
    token=current_owner.set(None)
    try:
        with pytest.raises(RuntimeError,match='signed-in'):await q.quick('pass',{'thread_id':'t'},None)
    finally:current_owner.reset(token)

def test_reused_runner_removes_stale_artifacts_and_symlinks(tmp_path):
    import subprocess,sys
    from pathlib import Path
    source=Path(__file__).resolve().parents[1]/'sandbox'
    tools=tmp_path/'tools';tools.mkdir();work=tmp_path/'work';work.mkdir()
    outside=tmp_path/'outside';outside.write_text('preserve')
    for name in ('quick.py','collect.py','checkpoint.py'):
        (tools/name).write_text((source/name).read_text().replace('/workspace',str(work)))
    def run(code,checkpoint=[]):
        r=subprocess.run([sys.executable,str(tools/'quick.py')],input=json.dumps({'code':code,'checkpoint':checkpoint}),text=True,capture_output=True,cwd=work,timeout=10)
        assert r.returncode==0,r.stderr
        return json.loads(r.stdout)
    first=run("from pathlib import Path\nPath('artifacts/old.txt').write_text('old')\nPath('keep.txt').write_text('saved')")
    (work/'stale').symlink_to(outside)
    second=run("from pathlib import Path\nprint(Path('keep.txt').read_text())",first['checkpoint']['files'])
    assert second['stdout'].strip()=='saved'
    assert not second['artifacts'] and not (work/'stale').exists()
    assert outside.read_text()=='preserve'
    third=run("from pathlib import Path\nPath('keep.txt').unlink()",second['checkpoint']['files'])
    fourth=run("from pathlib import Path\nprint(Path('keep.txt').exists())",third['checkpoint']['files'])
    assert fourth['stdout'].strip()=='False'
