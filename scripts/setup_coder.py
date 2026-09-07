import httpx,json,secrets,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local'
AI='--ai' in sys.argv
PREFIX='coder-ai' if AI else 'coder'
BASE='http://127.0.0.1:'+('7081' if AI else '7080')
c=httpx.Client(base_url=BASE,timeout=60,trust_env=False)
path=LOCAL/(PREFIX+'-admin.json')
if not path.exists():
    first=c.get('/api/v2/users/first')
    if first.status_code!=404: raise SystemExit('Coder already initialized. Supply local admin credentials in .local/coder-admin.json.')
    data={'email':'developer@lab.test','username':'developer','password':secrets.token_urlsafe(24),'trial':False}
    r=c.post('/api/v2/users/first',json=data); r.raise_for_status()
    path.write_text(json.dumps(data,indent=2)); path.chmod(0o600)
data=json.loads(path.read_text())
r=c.post('/api/v2/users/login',json={'email':data['email'],'password':data['password']}); r.raise_for_status()
token=r.json()['session_token']
p=LOCAL/(PREFIX+'-admin-token'); p.write_text(token); p.chmod(0o600)
c.headers['Coder-Session-Token']=token
org=c.get('/api/v2/organizations').json()[0]
(LOCAL/(PREFIX+'-org.json')).write_text(json.dumps(org))
for endpoint in ['/api/v2/chats','/api/experimental/chats','/api/v2/chats/providers','/api/experimental/chats/providers','/api/experimental/chats/model-configs','/api/v2/entitlements']:
    r=c.get(endpoint)
    try:
        j=r.json()
        if isinstance(j,dict): print(endpoint,r.status_code,'keys:',list(j.keys())[:12],str(j.get('message',''))[:100])
        elif isinstance(j,list): print(endpoint,r.status_code,'items:',len(j))
    except ValueError: print(endpoint,r.status_code,'not JSON')
print(f'Coder initialized. Login credentials saved in .local/{PREFIX}-admin.json.')
