"""Provision pinned native chat extensions from Open VSX into a GUI workspace."""
import argparse,datetime,hashlib,json,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PINS={'Anthropic/claude-code':'2.1.258','openai/chatgpt':'26.825.51511'}
def install(pod):
    base=['kubectl','--kubeconfig',str(ROOT/'.local/kubeconfig'),'-n','lab-dev']
    command=base+['exec',pod,'--']
    installed=subprocess.check_output(command+['code-server','--list-extensions','--show-versions'],text=True).lower()
    arch={'aarch64':'arm64','x86_64':'x64'}[subprocess.check_output(command+['uname','-m'],text=True).strip()]
    cache=ROOT/'.local/gui-harness-trial';cache.mkdir(parents=True,exist_ok=True)
    for extension,version in PINS.items():
        if extension.replace('/','.',1).lower()+'@'+version in installed:continue
        url='https://open-vsx.org/api/'+extension+'/linux-'+arch+'/'+version
        with urllib.request.urlopen(url,timeout=30) as response:meta=json.load(response)
        published=datetime.datetime.fromisoformat(meta['timestamp'].replace('Z','+00:00'))
        if datetime.datetime.now(datetime.timezone.utc)-published<datetime.timedelta(days=5):raise RuntimeError('Extension release too new')
        files=meta['files']
        if not all(files[k].startswith('https://open-vsx.org/') for k in ['download','sha256']):raise RuntimeError('Unexpected extension registry')
        with urllib.request.urlopen(files['sha256'],timeout=30) as response:sha=response.read(1024).decode().split()[0]
        path=cache/(extension.replace('/','-')+'-'+version+'-'+arch+'.vsix')
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            with urllib.request.urlopen(files['download'],timeout=90) as response:data=response.read(250_000_001)
            if len(data)>250_000_000 or hashlib.sha256(data).hexdigest()!=sha:raise RuntimeError('Extension size/integrity check failed')
            path.write_bytes(data)
        target='/tmp/'+path.name
        subprocess.run(base+['cp',str(path),'lab-dev/'+pod+':'+target],check=True)
        subprocess.run(command+['code-server','--install-extension',target,'--force'],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(command+['rm',target],check=True)
    print('Native Claude Code and Codex extensions ready.')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pod',required=True);install(parser.parse_args().pod)
