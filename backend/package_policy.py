"""Human control-plane package approvals; never exposed as a model tool."""
import asyncio,json,re,time
from fastapi import HTTPException
from .config import ROOT,STATE
LOCK=asyncio.Lock()
PATH=ROOT/'infra/packages.json'
def read():return json.loads(PATH.read_text())
async def change(data,owner):
    ecosystem=data.get('ecosystem');name=str(data.get('package','')).strip();version=str(data.get('version','')).strip();reason=str(data.get('reason','')).strip()
    if ecosystem not in ['python','npm','cargo','go','nuget','julia']:raise HTTPException(400,'Unknown ecosystem')
    pattern=r'(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]{1,160}' if ecosystem=='npm' else r'[A-Za-z0-9!._~/-]{1,240}'
    if not re.fullmatch(pattern,name) or '..' in name:raise HTTPException(400,'Invalid package name')
    if not 5<=len(reason)<=500:raise HTTPException(400,'Add a brief approval reason')
    if version and (not re.fullmatch('[A-Za-z0-9.+_-]{1,120}',version)):raise HTTPException(400,'Use one exact version or content hash')
    if not data.get('override_age') or not version:raise HTTPException(400,'Packages need no approval. An age exception needs an exact version.')
    if ecosystem in ['python','nuget']:name=name.lower()
    if ecosystem=='python':name=re.sub('[-_.]+','-',name)
    async with LOCK:
        value=read();value.pop('packages',None)
        if data.get('override_age'):
            value['overrides']=[v for v in value.get('overrides',[]) if v.get('expires',0)>time.time()]
            value['overrides'].append({'ecosystem':ecosystem,'package':name,'version':version,'expires':int(time.time())+86400,'reason':reason})
        manifest={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'package-policy','namespace':'lab-control'},'data':{'packages.json':json.dumps(value,indent=2)}}
        process=await asyncio.create_subprocess_exec('kubectl','--kubeconfig',str(STATE/'kubeconfig'),'apply','-f','-',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            await asyncio.wait_for(process.communicate(json.dumps(manifest).encode()),20)
            if process.returncode:raise HTTPException(503,'Could not apply the package policy')
        finally:
            if process.returncode is None:process.kill();await process.wait()
        PATH.write_text(json.dumps(value,indent=2)+'\n')
        with (STATE/'package-policy-audit.jsonl').open('a') as log:log.write(json.dumps({'at':time.time(),'owner':owner,'ecosystem':ecosystem,'package':name,'version':version,'override_age':bool(data.get('override_age')),'reason':reason})+'\n')
    return {'saved':True,'message':'Policy saved. Kubernetes may take about a minute to refresh the gateway policy.'}
