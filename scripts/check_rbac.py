import subprocess,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
checks=[('broker','lab-sandboxes','get','secrets','lab-sandboxes',False),('broker','lab-sandboxes','create','pods','lab-dev',False),('broker','lab-sandboxes','create','pods','lab-agents',False),('coder','coder','create','pods','lab-dev',True),('coder','coder','create','pods','lab-agents',False),('coder','coder-ai','create','pods','lab-agents',True),('coder','coder-ai','create','pods','lab-dev',False)]
results=[]
for name,sa_ns,verb,resource,ns,expected in checks:
    p=subprocess.run(['kubectl','--kubeconfig',str(root/'.local/kubeconfig'),'auth','can-i',verb,resource,'-n',ns,f'--as=system:serviceaccount:{sa_ns}:{name}'],capture_output=True,text=True)
    actual=p.stdout.strip()=='yes'
    results.append({'identity':f'{sa_ns}/{name}','action':f'{verb} {resource} in {ns}','allowed':actual,'passed':actual==expected})
print(json.dumps(results,indent=2))
assert all(r['passed'] for r in results)
