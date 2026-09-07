import json,secrets,os
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]; LOCAL=ROOT/'.local'
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
c=httpx.Client(base_url='http://127.0.0.1:7081',headers={'Coder-Session-Token':(LOCAL/'coder-ai-admin-token').read_text().strip()},timeout=60,trust_env=False)
def request(method,path,**kw):
    r=c.request(method,path,**kw)
    if r.status_code>=400:
        try: j=r.json(); message=j.get('message','')+' '+j.get('detail','')
        except ValueError: message='Non-JSON error'
        raise RuntimeError(f'{path}: {r.status_code} {message[:600]}')
    return r.json() if r.content else {}
# Coder always manages workspace connectivity. The selected engine owns inference.
# Disable the native provider when running the Ori/Pi profile.
providers=request('GET','/api/v2/ai/providers')
for provider in providers:
    if provider['name']=='lab-openrouter' and os.getenv('PROJECT_ENGINE','ori-pi')!='coder-native':
        request('PATCH','/api/v2/ai/providers/'+provider['id'],json={'enabled':False,'api_keys':[]})
org=json.loads((LOCAL/'coder-ai-org.json').read_text())
path=LOCAL/'coder-ai-service-account.json'
if not path.exists():
    cred={'email':'chat-sandbox@lab.test','username':'chat-sandbox','password':secrets.token_urlsafe(24),'organization_ids':[org['id']]}
    user=request('POST','/api/v2/users',json=cred)
    cred['id']=user['id']; path.write_text(json.dumps(cred)); path.chmod(0o600)
cred=json.loads(path.read_text())
request('PUT',f'/api/v2/organizations/{org["id"]}/members/{cred["id"]}/roles',json={'roles':['agents-access']})
auth=httpx.post('http://127.0.0.1:7081/api/v2/users/login',json={'email':cred['email'],'password':cred['password']},timeout=30,trust_env=False)
auth.raise_for_status()
token=auth.json()['session_token']
templates=request('GET',f'/api/v2/organizations/{org["id"]}/templates')
headless=next(t for t in templates if t['name']=='ai-headless')
# This deployment contains only headless templates. Isolation does not rely on Premium template RBAC.
if any(t['name'] != 'ai-headless' for t in templates): raise RuntimeError('Unexpected template in the AI-only deployment')
config={'token':token,'organization_id':org['id'],'template_id':headless['id'],'service_user_id':cred['id'],'api_prefix':'/api/experimental/chats'}
p=LOCAL/'coder-integration.json'; p.write_text(json.dumps(config)); p.chmod(0o600)
print('Coder workspace identity configured. Engine:',os.getenv('PROJECT_ENGINE','ori-pi'))
