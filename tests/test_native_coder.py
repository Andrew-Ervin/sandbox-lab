import asyncio
import pytest
from backend.native_coder import results,messages_after

def test_native_results_keep_tool_arguments_and_assistant_text():
    summary,tools=results([
        {'role':'user','content':[{'type':'text','text':'not an answer'}]},
        {'role':'assistant','content':[{'type':'tool-call','tool_name':'execute','args':{'command':'uv run main.py'}},{'type':'text','text':'Done'}]},
    ])
    assert summary=='Done'
    assert tools[0]['tool']=='execute'
    assert 'uv run main.py' in tools[0]['code']

def test_native_pagination_collects_complete_turn_in_order():
    class API:
        async def api(self,method,path,params):
            before=params.get('before_id',5)
            rows=[{'id':i} for i in range(before-1,max(0,before-3),-1)]
            return {'messages':rows,'has_more':before>3}
    assert asyncio.run(messages_after(API(),'/messages',1))==[{'id':2},{'id':3},{'id':4}]

def test_native_pagination_rejects_nonadvancing_server():
    class API:
        async def api(self,*args,**kwargs):return {'messages':[{'id':4}],'has_more':True}
    with pytest.raises(RuntimeError,match='did not advance'):
        asyncio.run(messages_after(API(),'/messages'))

def test_trial_manifest_blocks_headless_model_route_but_keeps_packages():
    import yaml
    from pathlib import Path
    docs=list(yaml.safe_load_all(Path('infra/lab.yaml').read_text()))
    policy=next(d for d in docs if d['kind']=='NetworkPolicy' and d['metadata'].get('namespace')=='lab-agents' and d['metadata']['name']=='allowed-egress')
    ports={p['port'] for rule in policy['spec']['egress'] for p in rule.get('ports',[])}
    assert 8080 not in ports
    assert 3128 in ports
    gateway=next(d for d in docs if d['kind']=='NetworkPolicy' and d['metadata']['name']=='model-gateway')
    allowed=[peer['namespaceSelector']['matchLabels']['kubernetes.io/metadata.name'] for rule in gateway['spec']['ingress'] for peer in rule['from']]
    assert allowed==['lab-dev']
