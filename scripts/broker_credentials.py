"""Renew the local broker's scoped token; operator authority stays in this launcher."""
import base64,json,os,subprocess,sys,time,yaml
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.config import STATE
from backend.limits import value

def expires(path):
    try:
        token=yaml.safe_load(path.read_text())['users'][0]['user']['token']
        payload=token.split('.')[1]
        return float(json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))['exp'])
    except (OSError,ValueError,KeyError,IndexError,TypeError,yaml.YAMLError):return 0

def renew():
    out=STATE/'broker-kubeconfig'
    if expires(out)>time.time()+value('BROKER_RENEW_BEFORE_SECONDS'):return False
    source=yaml.safe_load((STATE/'kubeconfig').read_text())
    result=subprocess.run(['kubectl','--kubeconfig',str(STATE/'kubeconfig'),'-n','lab-sandboxes','create','token','broker','--duration='+str(value('BROKER_TOKEN_SECONDS'))+'s'],capture_output=True,text=True,timeout=30)
    if result.returncode:raise RuntimeError('Could not renew the scoped Kubernetes broker credential; check local cluster/operator access.')
    source['users']=[{'name':'broker','user':{'token':result.stdout.strip()}}]
    for context in source['contexts']:context['context'].update(user='broker',namespace='lab-sandboxes')
    temporary=out.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:yaml.safe_dump(source,stream);stream.flush();os.fsync(stream.fileno())
    temporary.chmod(0o600);temporary.replace(out)
    print('Scoped broker credential renewed.',flush=True)
    return True

def main():
    while True:
        try:renew()
        except Exception:
            print('Broker credential renewal failed; check local cluster/operator access.',file=sys.stderr,flush=True)
            if '--watch' not in sys.argv:return 1
        if '--watch' not in sys.argv:return 0
        time.sleep(30)

if __name__=='__main__':sys.exit(main())
