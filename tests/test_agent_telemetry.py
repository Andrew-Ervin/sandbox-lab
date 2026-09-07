from backend.agent_telemetry import snapshot
from backend.app_links import app_links


def test_native_activity_tracks_results_usage_and_only_provider_reasoning(monkeypatch):
    records=[{'id':1,'role':'user','content':[{'type':'reasoning','text':'never show user metadata'}]},
      {'id':2,'role':'assistant','usage':{'input_tokens':42,'output_tokens':10,'reasoning_tokens':3},'content':[
        {'type':'reasoning','text':'Check boundary cases first.'},
        {'type':'tool-call','tool_call_id':'1','tool_name':'execute','args':{'command':'cargo test'}}]},
      {'id':3,'role':'tool','content':[{'type':'tool-result','tool_call_id':'1','is_error':True}]}]
    result=snapshot(records)
    assert result['tool_calls']==1 and result['usage']['reasoning_tokens']==3
    assert 'execute · failed' in result['details'] and 'Check boundary cases first.' in result['details']
    assert 'never show' not in result['details']
    monkeypatch.setenv('NATIVE_TELEMETRY_MAX_CHARS','10')
    result=snapshot(records)
    assert result['truncated'] and len(result['details'])<=10


def test_only_internal_app_links_use_native_deeplinks():
    run='run_'+'a'*32
    original=f'[Open app](http://127.0.0.1:3000/api/app-preview/{run})'
    assert app_links(original)==f'[Open app](chatkit-link://app-{run})'
    assert app_links('[Docs](https://example.org/api/app-preview/'+run+')').startswith('[Docs](https:')
    assert app_links(app_links(original))==app_links(original)


def test_artifact_deeplinks_and_nested_output_fences():
    from backend.markdown import fenced
    run='run_'+'b'*32
    assert app_links(f'[Plot](http://localhost:3000/api/artifact-view/{run}/plot.html)')==f'[Plot](chatkit-link://file-{run}-706c6f742e68746d6c)'
    assert '/..' in app_links(f'[No](http://localhost:3000/api/artifact-view/{run}/../secret)')
    output='Nested\n```python\nprint(1)\n```'
    assert fenced(output).startswith('````text\n') and fenced(output).endswith('\n````')
