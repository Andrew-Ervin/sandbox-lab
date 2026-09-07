import subprocess,sys,os,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
python=str(root/'.venv/bin/python')
nodes=json.loads(subprocess.check_output(['kubectl','--kubeconfig',str(root/'.local/kubeconfig'),'get','nodes','-o','json']))
architectures={n['status']['nodeInfo']['architecture'] for n in nodes['items']}
if len(architectures)!=1 or not architectures.issubset({'amd64','arm64'}): raise RuntimeError('Select an explicit template/node-pool architecture for a mixed or unsupported cluster')
architecture=architectures.pop()
for ai,name,ns,image,gui,url in [(False,'developer','lab-dev',os.getenv('DEVELOPER_IMAGE','sandbox-lab/developer:local'),'true','http://coder.coder.svc.cluster.local:7080'),(True,'ai-headless','lab-agents',os.getenv('AI_IMAGE','sandbox-lab/ai:local'),'false','http://coder.coder-ai.svc.cluster.local:7080')]:
    command=[python,str(root/'scripts/coder_cli.py'),*(['--ai'] if ai else []),'templates','push',name,'--directory',str(root/'infra/coder'),'--variable','architecture='+architecture,'--variable','namespace='+ns,'--variable','image='+image,'--variable','gui='+gui,'--variable','coder_url='+url,'--yes']
    subprocess.run(command,check=True,cwd=root)
