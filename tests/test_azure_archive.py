import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.azure_archive import AzureArchive

class Storage:
    enabled=True
    def __init__(self):self.data={}
    async def save(self,kind,key,payload):self.data[key]=payload
    async def load(self,kind,key):return self.data.get(key)

@pytest.mark.asyncio
async def test_archive_verifies_roundtrip_and_rejects_corrupt_chunk(tmp_path):
    storage=Storage();archive=AzureArchive(SimpleNamespace(storage=storage))
    source=tmp_path/'source.tgz';source.write_bytes(b'private-test-file'*100)
    key=await archive.upload('workspace',source)
    output=tmp_path/'restored.tgz';await archive.download('workspace',key,output)
    assert output.read_bytes()==source.read_bytes()
    chunk=storage.data[key]['chunks'][0]['key'];storage.data[chunk]['data']='Y29ycnVwdA=='
    with pytest.raises(RuntimeError,match='verification'):await archive.download('workspace',key,tmp_path/'bad')


def test_archive_requires_seven_days_stopped_and_explicit_policy(monkeypatch):
    monkeypatch.setattr('backend.azure_archive.time.time',lambda:10*86400)
    runtime=SimpleNamespace(config={'archive_after_days':7},storage=Storage(),resizing=set())
    archive=AzureArchive(runtime)
    record={'id':'w','kind':'headless','state':'stopped','sandbox_id':'s','last_activity_at':86400}
    assert archive.eligible(record)
    for change in ({'state':'running'},{'warm':True},{'disposable':True},{'last_activity_at':9*86400},{'cold_archive':'saved'}):
        assert not archive.eligible({**record,**change})
    runtime.config={};assert not archive.eligible(record)

@pytest.mark.asyncio
async def test_failed_archive_never_deletes_source(tmp_path,monkeypatch):
    record={'id':'w','name':'test','kind':'headless','state':'stopped','sandbox_id':'s','last_activity_at':1,'updated_at':1}
    runtime=SimpleNamespace(config={'archive_after_days':7},storage=Storage(),resizing=set(),workspace_locks={},root=tmp_path,
        record=lambda wid:dict(record),save=lambda value:record.update(value),_start=AsyncMock(),_stop=AsyncMock(),export_home=AsyncMock(side_effect=RuntimeError('failed')),
        profile=lambda kind:{'group':'test'},transport=SimpleNamespace(call=AsyncMock(return_value={'state':'Stopped'})),telemetry=SimpleNamespace(event=lambda *a,**kw:None))
    archive=AzureArchive(runtime);archive.freeze=AsyncMock()
    await archive.archive('w')
    assert [c.args[0] for c in runtime.transport.call.call_args_list]==['get']
    assert record['sandbox_id']=='s' and 'cold_archive' not in record
    assert 'w' not in runtime.resizing
