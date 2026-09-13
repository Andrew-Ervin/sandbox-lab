"""Run the explicitly approved custom-session test, then remove its compute.

Requires the private fixed-cost approval record. Creates no registry, network,
volume, or logging workspace. Run only after the separate environment template.
"""
import argparse
from datetime import datetime,timezone
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid
import urllib.request
import urllib.error
import urllib.parse

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
POOL='labpythoncustom'


def az(*args, timeout=180):
    return subprocess.run(['sh',str(ROOT/'scripts/azure_pilot_az.sh'),*args,'-o','json'],capture_output=True,text=True,timeout=timeout)


def checked(*args, timeout=180):
    result=az(*args,timeout=timeout)
    if result.returncode: raise RuntimeError(result.stderr[:2000])
    return json.loads(result.stdout) if result.stdout.strip() else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-approved-test',action='store_true')
    parser.add_argument('--retry-after-confirmed-cleanup',action='store_true')
    args=parser.parse_args()
    if not args.run_approved_test: parser.error('Explicit test flag required')
    from backend.azure_runtime import AzureRuntime
    control=AzureRuntime();config=control.config
    approvals=config.get('fixed_cost_approvals',[])
    if not any(x['resource']=='lab-python-custom-two-hour-test' and x['allowance_usd']==5 for x in approvals):
        raise RuntimeError('The dedicated session test has no recorded fixed-cost approval')
    path=ROOT/'.local/azure-pilot/custom-session-receipt.json'
    prior=json.loads(path.read_text()) if path.exists() else {}
    deadline=config.get('session_test_deadline',0)
    if deadline<time.time()+900:raise RuntimeError('The approved test window has ended or has too little cleanup time remaining')
    if prior.get('python_and_checkpoint'):raise RuntimeError('This approved test has already completed')
    if prior.get('cleanup_confirmed') and not args.retry_after_confirmed_cleanup:raise RuntimeError('Retry requires a confirmed cleanup and explicit retry flag')
    if args.retry_after_confirmed_cleanup and not prior.get('cleanup_confirmed'):raise RuntimeError('Previous pool and environment cleanup must be confirmed before retry')
    previous_estimate=float(prior.get('conservative_dedicated_estimate_usd',0))
    charge=(control.budget.reserve('custom-sessions-test',5-previous_estimate) if prior.get('cleanup_confirmed') else prior.get('charge')) or control.budget.reserve('custom-sessions-test',5)
    started=prior.get('started',time.time())
    receipt={**prior,'started':started,'deadline':deadline,'maximum_nodes':1,'charge':charge,'cleanup_confirmed':False}
    if prior.get('failure'):receipt.setdefault('prior_failures',[]).append(prior['failure'])
    receipt.pop('failure',None)
    for key in ('node_count','endpoint','first_request_seconds','second_request_seconds','python_passed','python_and_checkpoint','platform_rejections','pool_deleted_at','cleanup_started'):
        receipt.pop(key,None)
    path.write_text(json.dumps(receipt,indent=2));path.chmod(0o600)
    scope='/subscriptions/'+config['subscription_id']+'/resourceGroups/'+config['resource_group']
    pool_id=scope+'/providers/Microsoft.App/sessionPools/'+POOL
    environment=config.get('session_test_environment','lab-session-test')
    env_id=scope+'/providers/Microsoft.App/managedEnvironments/'+environment
    receipt['environment']=environment
    image=config.get('session_test_image')
    if not isinstance(image,str) or not re.fullmatch(r'[^/]+\.azurecr\.io/sandbox-lab/python@sha256:[a-f0-9]{64}',image):
        raise RuntimeError('Private runtime configuration must supply an immutable Azure Container Registry image digest')
    executor_id=config.get('session_test_executor_object_id')
    try: uuid.UUID(str(executor_id))
    except (ValueError,TypeError,AttributeError): raise RuntimeError('Private runtime configuration must supply the Session Executor object ID')
    try:
        # This is a named ARM PUT; timeout recovery inspects the same resource.
        receipt['deployment_started']=time.time();path.write_text(json.dumps(receipt,indent=2))
        checked('deployment','group','create','-g',config['resource_group'],'-n','lab-custom-python-session',
            '--template-file',str(ROOT/'infra/azure-sandbox-pilot/custom-sessions.json'),'--parameters',
            'image='+image,
            'registryServer='+image.split('/',1)[0],'environmentName='+environment,'deleteAfter='+datetime.fromtimestamp(deadline,timezone.utc).isoformat(),timeout=min(1200,int(deadline-time.time()-600)))
        pool=checked('rest','--method','GET','--url','https://management.azure.com'+pool_id+'?api-version=2025-07-01')
        receipt['node_count']=pool['properties'].get('nodeCount');receipt['endpoint']=pool['properties'].get('poolManagementEndpoint')
        if receipt['node_count'] is not None and receipt['node_count']>1:raise RuntimeError('Pool exceeds approved one-node capacity')
        checked('role','assignment','create','--assignee-object-id',str(executor_id),'--assignee-principal-type','User',
            '--role','Azure ContainerApps Session Executor','--scope',pool_id)
        token=checked('account','get-access-token','--resource','https://dynamicsessions.io')['accessToken']
        endpoint=receipt['endpoint']
        if not endpoint or not endpoint.startswith('https://') or not urllib.parse.urlsplit(endpoint).hostname.endswith('.azurecontainerapps.io'):
            raise RuntimeError('Unexpected session endpoint')
        identifier='lab-test-'+uuid.uuid4().hex
        def request(route, body):
            url=endpoint.rstrip('/')+route+'?'+urllib.parse.urlencode({'api-version':'2025-02-02-preview','identifier':identifier})
            data=json.dumps(body).encode()
            with urllib.request.urlopen(urllib.request.Request(url,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}),timeout=120) as response:
                raw=response.read(70_000_001)
                if len(raw)>70_000_000:raise RuntimeError('Oversized session response')
                return json.loads(raw)
        def synthetic_request(body):
            for attempt in range(20):
                if time.time()>deadline-600:raise RuntimeError('Test stopped to leave cleanup time within its approved window')
                try:return request('/execute',body)
                except urllib.error.HTTPError as error:
                    diagnostic=error.read(1500).decode(errors='replace')
                    receipt.setdefault('platform_rejections',[]).append({'status':error.code,'message':diagnostic,'at':time.time()})
                    path.write_text(json.dumps(receipt,indent=2))
                    # These synthetic calls write a fixed test file or read it;
                    # repeat only explicit platform rejections, never timeouts.
                    if error.code not in (403,429,503):raise
                    time.sleep(15)
            raise RuntimeError('Session did not become ready')
        begin=time.monotonic()
        result=synthetic_request({'code':"import polars as pl; import scipy; from pathlib import Path; Path('state.txt').write_text('kept'); print(pl.DataFrame({'n':[20,22]}).select(pl.col('n').sum()).item())"})
        receipt['first_request_seconds']=round(time.monotonic()-begin,3)
        assert result['exit_code']==0 and result['stdout'].strip()=='42',result
        receipt['python_passed']=True;path.write_text(json.dumps(receipt,indent=2))
        begin=time.monotonic()
        result=synthetic_request({'code':"from pathlib import Path; print(Path('state.txt').read_text())",'checkpoint':result['checkpoint']['files']})
        receipt['second_request_seconds']=round(time.monotonic()-begin,3)
        assert result['exit_code']==0 and result['stdout'].strip()=='kept',result
        receipt['python_and_checkpoint']=True
        pool=checked('rest','--method','GET','--url','https://management.azure.com'+pool_id+'?api-version=2025-07-01')
        receipt['node_count']=pool['properties'].get('nodeCount')
        print(json.dumps({k:v for k,v in receipt.items() if k not in ('endpoint','charge')}),flush=True)
    except Exception as error:
        receipt['failure']=str(error)[:4000]
        path.write_text(json.dumps(receipt,indent=2))
        raise
    finally:
        receipt['cleanup_started']=time.time();path.write_text(json.dumps(receipt,indent=2))
        # Deleting the pool, rather than trusting zero ready sessions, releases
        # dedicated capacity. Unknown deletion keeps the full $5 reservation.
        try:
            for resource,version in [(pool_id,'2025-07-01'),(env_id,'2025-07-01')]:
                result=az('rest','--method','DELETE','--url','https://management.azure.com'+resource+'?api-version='+version)
                if result.returncode and 'ResourceNotFound' not in result.stderr:raise RuntimeError(result.stderr[:1000])
                for _ in range(360):
                    probe=az('rest','--method','GET','--url','https://management.azure.com'+resource+'?api-version='+version)
                    if probe.returncode and ('ResourceNotFound' in probe.stderr or 'NotFound' in probe.stderr):break
                    time.sleep(5)
                else:raise RuntimeError('Dedicated cleanup not confirmed')
                if resource==pool_id:
                    receipt['pool_deleted_at']=time.time()
                    path.write_text(json.dumps(receipt,indent=2))
            receipt['cleanup_confirmed']=True
            receipt['ended']=time.time()
            estimate=(receipt['pool_deleted_at']-started)/3600*1.650416
            control.budget.finish(charge,max(0,estimate-previous_estimate));receipt['conservative_dedicated_estimate_usd']=estimate
        finally:
            receipt['budget']=control.budget.status();path.write_text(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
