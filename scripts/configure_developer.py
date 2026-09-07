"""Configure Pi/Ori and its VS Code entry point without replacing workspace files."""
import argparse,asyncio,base64,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.developer import developer
from backend.capabilities import issue

async def main(name):
    ws=await developer.api('GET','/api/v2/users/me/workspace/'+name)
    from install_gui_extensions import install as install_native_extensions
    install_native_extensions('ws-'+ws['id'])
    data={**issue(ws['id']),'gui':True}
    data['ori_templates']={str(p.relative_to(ROOT/'sandbox/ori-templates')):p.read_text() for p in (ROOT/'sandbox/ori-templates').rglob('*') if p.is_file()}
    upstream=ROOT/'sandbox/pi-chat'
    data['package_setup']=(ROOT/'sandbox/package_setup.py').read_text()
    if upstream.is_dir():data['upstream_vsix']=base64.b64encode((upstream/'pi-chat.vsix').read_bytes()).decode()
    subprocess.run(['kubectl','--kubeconfig',str(ROOT/'.local/kubeconfig'),'-n','lab-dev','exec','-i','ws-'+ws['id'],'--','python','-c',(ROOT/'sandbox/harness_setup.py').read_text()],input=json.dumps(data),text=True,check=True)
    from backend.experiments import experiment
    experiment.configure_gui(ws['id'])
    print('Pi through Ori is the default workspace coding agent. Model access: one-hour credential, no request-count allowance.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',default='dev');args=p.parse_args();asyncio.run(main(args.workspace))
