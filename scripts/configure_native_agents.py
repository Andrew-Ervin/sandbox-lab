"""Configure native Coder inference only in the AI control plane; never print secrets."""
import json,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.config import STATE,API_KEY,MODEL,REASONING

def main():
    if not API_KEY:raise RuntimeError('OPENROUTER_API_KEY is required')
    trial=STATE/'native-coder-trial';trial.mkdir(exist_ok=True)
    c=httpx.Client(base_url='http://127.0.0.1:7081',headers={'Coder-Session-Token':(STATE/'coder-ai-admin-token').read_text().strip()},trust_env=False,timeout=60)
    def request(method,path,**kw):
        r=c.request(method,path,**kw)
        if r.status_code>=400:raise RuntimeError(f'Native Coder setup: {method} {path}: HTTP {r.status_code}')
        return r.json() if r.content else {}
    prefix='/api/experimental/chats'
    providers=request('GET','/api/v2/ai/providers')
    provider=next((p for p in providers if p['name']=='lab-openrouter'),None)
    models=request('GET',prefix+'/model-configs')
    snapshot=trial/'native-before.json'
    if not snapshot.exists():
        snapshot.write_text(json.dumps({'provider':provider,'models':models}));snapshot.chmod(0o600)
    if provider:
        request('PATCH','/api/v2/ai/providers/'+provider['id'],json={'enabled':True,'api_keys':[{'api_key':API_KEY}]})
    else:
        provider=request('POST','/api/v2/ai/providers',json={'type':'openrouter','name':'lab-openrouter','display_name':'OpenRouter','enabled':True,'base_url':'https://openrouter.ai/api/v1','api_keys':[API_KEY]})
    model=next((m for m in models if m['model']==MODEL),None)
    body={'ai_provider_id':provider['id'],'model':MODEL,'display_name':MODEL+' · '+REASONING,'enabled':True,'is_default':True,'context_limit':1050000,'model_config':{'max_output_tokens':16000,'reasoning_effort':{'default':REASONING,'max':REASONING},'provider_options':{'openrouter':{'extra_body':{'provider':{'zdr':True,'data_collection':'deny'}}}}}}
    model=request('PATCH',prefix+'/model-configs/'+model['id'],json=body) if model else request('POST',prefix+'/model-configs',json=body)
    path=STATE/'native-coder.json';path.write_text(json.dumps({'api_prefix':prefix,'model_config_id':model['id'],'model':MODEL,'reasoning':REASONING}));path.chmod(0o600)
    print('Native Coder configured:',MODEL,REASONING,'; provider key stored only in Coder control plane.')

if __name__=='__main__':main()
