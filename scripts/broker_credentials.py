import subprocess,yaml,os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
local=root/'.local'
source=yaml.safe_load((local/'kubeconfig').read_text())
p=subprocess.run(['kubectl','--kubeconfig',str(local/'kubeconfig'),'-n','lab-sandboxes','create','token','broker','--duration=24h'],capture_output=True,text=True,check=True)
source['users']=[{'name':'broker','user':{'token':p.stdout.strip()}}]
for c in source['contexts']: c['context'].update(user='broker',namespace='lab-sandboxes')
out=local/'broker-kubeconfig'
fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f: yaml.safe_dump(source,f)
print('Scoped broker credential saved (24-hour lifetime).')
