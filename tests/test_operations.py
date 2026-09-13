from types import SimpleNamespace
from backend.telemetry import Telemetry


def test_telemetry_redacts_credentials_and_distinguishes_allocation(tmp_path):
    telemetry=Telemetry(tmp_path/'events.db')
    telemetry.event('quick','one','command_failed',seconds=.2,error='Bearer synthetic-secret')
    runtime=SimpleNamespace(records=lambda kind: [{'id':'one','state':'running','warm':True}] if kind=='quick' else [],profile=lambda kind:{'cpu':'1000m','memory':'2048Mi'},allocation=lambda record:{'cpu':'1000m','memory':'2048Mi'},active_commands={},queued={'quick':3},budget=SimpleNamespace(status=lambda:{'estimated_and_reserved_usd':1}))
    telemetry.sample(runtime)
    snapshot=telemetry.snapshot()
    assert 'synthetic-secret' not in str(snapshot)
    assert snapshot['allocation_is_not_cpu_utilization']
    assert snapshot['samples'][0]['roles']['quick']=={'running':1,'warm':1,'busy':0,'queued':3,'cpu':1,'memory_gib':2,'retained':1}
    assert snapshot['events'][0]['error']=='Bearer [redacted]'
    assert snapshot['totals'][0]['failures']==1
