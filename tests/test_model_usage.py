import json
from datetime import datetime,timezone
from backend.model_usage import UsageLedger,extract

def test_sse_final_usage_and_cache_is_not_double_counted(tmp_path):
    raw=b'data: {"choices":[{"delta":{"content":"private text"}}]}\n\ndata: {"id":"gen-test","usage":{"prompt_tokens":100,"completion_tokens":20,"prompt_tokens_details":{"cached_tokens":80},"cost":0.001}}\n\ndata: [DONE]\n\n'
    ledger=UsageLedger(tmp_path/'usage.sqlite');now=datetime(2026,9,14,12,tzinfo=timezone.utc)
    for _ in range(2):ledger.record('one','alice','model','completions',raw,now.timestamp())
    ledger.record('two','bob','model','completions',raw,now.timestamp())
    p=ledger.summary('alice',now)['periods']['today']
    assert p['requests']==1 and p['input_tokens']==100 and p['cached_tokens']==80 and p['cost']==.001
    assert 'private text' not in (tmp_path/'usage.sqlite').read_bytes().decode(errors='ignore')

def test_native_usage_merges_and_missing_cost_is_unknown():
    raw=b'data: {"message":{"usage":{"input_tokens":10,"cache_read_input_tokens":90,"cache_creation_input_tokens":5}}}\n\ndata: {"usage":{"output_tokens":12}}\n\n'
    u=extract(raw);assert u['input_tokens']==105 and u['output_tokens']==12 and u['cost'] is None
    u=extract(json.dumps({'response':{'usage':{'input_tokens':100,'output_tokens':20,'cost':0,'input_tokens_details':{'cached_tokens':50}}}}).encode())
    assert u['cost']==0 and u['input_tokens']==100 and u['cached_tokens']==50
    assert extract(b'{}')['cost'] is None
    assert extract(b'{"usage":{"cost":"NaN"}}')['cost'] is None

def test_calendar_periods_and_owner_isolation(tmp_path):
    l=UsageLedger(tmp_path/'usage.sqlite');now=datetime(2026,9,14,12,tzinfo=timezone.utc)
    for i,date in enumerate(['2025-12-31','2026-01-01','2026-09-01','2026-09-13','2026-09-14']):
        l.record(str(i),'a','m','responses',b'{"usage":{"cost":1}}',datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())
    p=l.summary('a',now)['periods'];assert [p[k]['cost'] for k in ('today','week','month','year')]==[1,1,3,4]
    assert l.summary('b',now)['periods']['year']['cost'] is None
