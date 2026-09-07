"""Apply secrets over stdin; never place secret values in argv or rendered manifests."""
import os,secrets,subprocess,json
from pathlib import Path
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1]
env=dotenv_values(root/'.env')
if not env.get('OPENROUTER_API_KEY') or not env.get('OPENROUTER_MODEL') or len(env.get('LAB_TOKEN_SECRET','').encode())<32:
    raise SystemExit('Set a provider key, model, and a random LAB_TOKEN_SECRET of at least 32 bytes in private .env')
local=root/'.local'
dbfile=local/'database-password'
if not dbfile.exists():
    dbfile.write_text(secrets.token_urlsafe(24)); dbfile.chmod(0o600)
password=dbfile.read_text().strip()
items=[('lab-control','model-credentials',{k:env[k] for k in ['OPENROUTER_API_KEY','OPENROUTER_MODEL','LAB_TOKEN_SECRET']}),('coder','database',{'password':password,'url':f'postgres://coder:{password}@postgres.coder.svc.cluster.local:5432/coder?sslmode=disable'})]
items[0][2].update(OPENROUTER_REASONING=env.get('OPENROUTER_REASONING','xhigh'),LAB_ALLOW_WEB_SEARCH=env.get('LAB_ALLOW_WEB_SEARCH','true'))
items.append(('coder-ai','database',{'password':password,'url':f'postgres://coder:{password}@postgres.coder-ai.svc.cluster.local:5432/coder?sslmode=disable'}))
for ns,name,data in items:
    obj={'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':ns},'type':'Opaque','stringData':data}
    p=subprocess.run(['kubectl','--kubeconfig',str(local/'kubeconfig'),'apply','-f','-'],input=json.dumps(obj),text=True,capture_output=True)
    if p.returncode: raise RuntimeError('Secret apply failed; check namespaces and cluster connection')
print('Applied model gateway and database credentials.')
