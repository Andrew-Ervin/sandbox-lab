"""Prepare local Azure runtime configuration/tools. Creates no Azure resources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def atomic(path, data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.chmod(0o600);temporary.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools',action='store_true',help='Download checksum-locked Linux AMD64 IDE and Ori binaries locally')
    parser.add_argument('--install',action='store_true',help='Install pinned CLI/SDK into separate private environments')
    parser.add_argument('--activate',action='store_true',help='Select Azure after live validation and persistent-storage review')
    parser.add_argument('--activate-for-validation',action='store_true',help='Select Azure temporarily to validate the rendered app after source migration')
    parser.add_argument('--prices',action='store_true',help='Read current OpenRouter model prices without making inference calls')
    args=parser.parse_args()
    if args.install:
        uv=ROOT/'.local/bin/uv'
        if not uv.exists():raise RuntimeError('Install the verified uv binary using scripts/download_tools.py first.')
        for folder,package in [('az-venv','azure-cli==2.90.0'),('sdk-venv','azure-containerapps-sandbox==0.1.0b4')]:
            env=ROOT/'.local/azure-pilot'/folder
            if not env.exists():subprocess.run([str(uv),'venv','--python',sys.executable,str(env)],check=True)
            subprocess.run([str(uv),'pip','install','--python',str(env/'bin/python'),'--prerelease=allow','--exclude-newer','2026-09-07',package],check=True)
    root=ROOT/'.local/azure-runtime';path=root/'config.json'
    if path.exists():config=json.loads(path.read_text())
    else:
        ledger=json.loads((ROOT/'.local/azure-pilot/ledger.json').read_text())
        config={'subscription_id':ledger['subscription_id'],'resource_group':ledger['resource_group'],'region':'eastus2',
                'persistent_storage_reviewed':False,'initial_compute_usd':max(.01,ledger.get('estimated_incurred_pilot_compute_cost',0))}
    if args.prices:
        from backend.config import MODEL
        with urllib.request.urlopen('https://openrouter.ai/api/v1/models',timeout=30) as response:models=json.load(response)['data']
        model=next((m for m in models if m['id']==MODEL),None)
        if not model:raise RuntimeError('The configured model has no verified public price; model admission remains closed.')
        pricing=model['pricing']
        config['model_prices']={'model':MODEL,'prompt':float(pricing['prompt']),'completion':float(pricing['completion']),
                                'source':'https://openrouter.ai/api/v1/models'}
    if args.tools:
        subprocess.run([sys.executable,str(ROOT/'scripts/download_editor_extensions.py')],check=True)
        lock=json.loads((ROOT/'scripts/tool-downloads.lock.json').read_text())
        for asset,name in [('code-server-4.106.3-linux-amd64.tar.gz','code-server-linux-amd64.tar.gz'),('ori-linux-x64','ori-linux-amd64')]:
            entry=lock[asset];target=ROOT/'.local/bin'/name
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==entry['sha256']:continue
            partial=target.with_suffix('.download');size=0
            with urllib.request.urlopen(entry['url'],timeout=90) as response,partial.open('wb') as output:
                while data:=response.read(1024*1024):
                    size+=len(data)
                    if size>250_000_000:raise RuntimeError('Tool archive exceeds its download limit')
                    output.write(data)
            if hashlib.sha256(partial.read_bytes()).hexdigest()!=entry['sha256']:
                partial.unlink();raise RuntimeError('Tool integrity check failed')
            partial.replace(target)
    atomic(path,config)
    if args.activate or args.activate_for_validation:
        validation=root/'validation.json'
        checks=json.loads(validation.read_text()) if validation.exists() else {}
        required=('quick','files','source_sync','preview_http','preview_websocket','developer_ide','developer_harness','package_age','stop_resume','cancellation','workload_images','migration')
        if args.activate_for_validation:
            required=tuple(k for k in required if k!='developer_ide')
        if not config.get('persistent_storage_reviewed') or not all(checks.get(k) is True for k in required):
            raise RuntimeError('Cutover is gated: complete live runtime checks and verify persistent-storage pricing before selecting Azure. Existing provider unchanged.')
        atomic(ROOT/'.local/compute-provider.json',{'provider':'azure','validation_in_progress':args.activate_for_validation})
        print('Azure selected. Restart scripts/start.py to use it; saved Azure files are retained.')
    else:print('Local Azure configuration prepared. No resource created and no provider cutover performed.')


if __name__=='__main__':main()
