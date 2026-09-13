"""Run inside the owning workspace. Persist/replay one app launch recipe, never a model turn."""
import fcntl,hashlib,json,os,re,socket,subprocess,time,sys,signal,shlex
from pathlib import Path
ROOT=Path('/home/sandbox/project').resolve()
STATE=Path.home()/'.local/state/lab';STATE.mkdir(parents=True,exist_ok=True)
RECIPE=ROOT/'.lab/app.json'

def select_source(path):
    global ROOT,RECIPE
    if not re.fullmatch(r'\.lab/imports/transfer_[a-f0-9]{32}',path):raise ValueError('Invalid source copy')
    folder=(ROOT/path).resolve()
    if not folder.is_relative_to(ROOT) or not folder.is_dir():raise ValueError('Source copy is not available')
    ROOT=folder;RECIPE=ROOT/'.lab/app.json'


def listening():
    try:
        with socket.create_connection(('127.0.0.1',3000),timeout=.4):return True
    except OSError:return False

def vite_script(script):
    """Recognize Vite behind the env/taskset wrappers used by saved apps."""
    try:parts=shlex.split(script)
    except ValueError:return False
    if parts and parts[0]=='env':
        parts=parts[1:]
        while parts:
            if parts[0]=='-u' and len(parts)>1:parts=parts[2:]
            elif re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*=.*',parts[0]):parts=parts[1:]
            else:break
    if len(parts)>=3 and parts[:2]==['taskset','-c'] and re.fullmatch(r'[0-9,-]+',parts[2]):parts=parts[3:]
    return bool(parts and parts[0]=='vite' and (len(parts)==1 or parts[1]!='build'))

def checked(data):
    cwd=(ROOT/data.get('cwd','.')).resolve()
    if not cwd.is_relative_to(ROOT) or not cwd.is_dir():raise ValueError('App folder must be inside the project.')
    argv=data.get('command')
    if not isinstance(argv,list) or not argv or len(argv)>64 or not all(isinstance(x,str) and 0<len(x)<4000 and '\x00' not in x for x in argv):raise ValueError('App recipe needs a command argument array.')
    # Vite ignores PORT and otherwise silently selects 5173/5174, which the
    # preview cannot reach. Normalize only recognized Vite npm scripts.
    manifest=cwd/'package.json'
    if len(argv)>=3 and argv[:2]==['npm','run'] and manifest.is_file():
        script=json.loads(manifest.read_text()).get('scripts',{}).get(argv[2],'')
        if vite_script(script):
            argv=list(argv)
            if '--' not in argv:argv.append('--')
            # Last CLI flags override script defaults; strictPort prevents fallback.
            argv+=['--host','0.0.0.0','--port','3000','--strictPort']
    return cwd,argv

def discover():
    # Prefer a saved explicit recipe. Migrate existing static/Go/Node prototypes.
    if RECIPE.exists():
        data=json.loads(RECIPE.read_text());checked(data);return data
    folders=[ROOT]+sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith('.'))
    for folder in folders:
        for output in ['dist','build','public']:
            if (folder/output/'index.html').is_file():
                return {'cwd':str(folder.relative_to(ROOT)),'command':['python','-m','http.server','3000','--bind','0.0.0.0','--directory',output]}
    for folder in folders:
        if (folder/'go.mod').is_file() or (folder/'main.go').is_file():
            # go run uses the preserved module/cache; missing downloads fail normally.
            return {'cwd':str(folder.relative_to(ROOT)),'command':['go','run','.'] if (folder/'go.mod').exists() else ['go','run','main.go']}
        if (folder/'package.json').is_file():
            scripts=json.loads((folder/'package.json').read_text()).get('scripts',{})
            if 'start' in scripts:return {'cwd':str(folder.relative_to(ROOT)),'command':['npm','run','start']}
            if 'dev' in scripts:return {'cwd':str(folder.relative_to(ROOT)),'command':['npm','run','dev','--','--host','0.0.0.0','--port','3000']}
        if (folder/'index.html').is_file():return {'cwd':str(folder.relative_to(ROOT)),'command':['python','-m','http.server','3000','--bind','0.0.0.0']}
    raise ValueError('No app launch recipe was found. Add .lab/app.json with cwd and command, then retry opening the app.')

def restore_packages(cwd,argv,env):
    # Source sync deliberately excludes node_modules. Recreate dependencies
    # through the configured gateway when the lockfile changes or they vanish.
    if Path(argv[0]).name!='npm' or not (cwd/'package.json').is_file():return
    manifest=cwd/'package.json';lock=cwd/'package-lock.json'
    if env.get('LAB_AZURE_RUNTIME')=='1' and lock.is_file():
        normalize_legacy_lock(lock)
    def digest():
        return hashlib.sha256(manifest.read_bytes()+(lock.read_bytes() if lock.is_file() else b'')).hexdigest()
    marker=STATE/('npm-'+hashlib.sha256(str(cwd).encode()).hexdigest()+'.sha256')
    if (cwd/'node_modules').is_dir() and marker.is_file() and marker.read_text()==digest():return
    command=['npm','ci' if lock.is_file() else 'install','--no-audit','--no-fund']
    with (STATE/'app.log').open('ab') as log:
        child=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=child.wait(timeout=int(os.getenv('APP_PACKAGE_RESTORE_SECONDS','120')))
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.wait()
            raise RuntimeError('App dependencies are still unavailable. Package restore timed out; inspect the workspace app log and retry.') from None
    if code:raise RuntimeError('App dependency restore failed. Check the workspace app log for package policy or lockfile errors.')
    marker.write_text(digest())

def normalize_legacy_lock(lock):
    """Remove provider-specific gateway addresses, retaining locked integrity.

    npm maps standard registry tarballs onto its configured registry. That route
    resolves fresh age-filtered metadata and checksums in the trusted gateway.
    """
    if lock.is_symlink() or lock.stat().st_size>16_000_000:raise ValueError('Unsafe app lockfile')
    original=lock.read_bytes();data=json.loads(original);changed=False
    for path,entry in data.get('packages',{}).items():
        if not isinstance(entry,dict):continue
        resolved=entry.get('resolved','')
        if not isinstance(resolved,str) or not re.fullmatch(r'http://package-proxy\.lab-control\.svc\.cluster\.local:3128/artifact/[a-f0-9]{64}',resolved):continue
        name=entry.get('name') or path.rsplit('node_modules/',1)[-1]
        version=entry.get('version','')
        if not re.fullmatch(r'(?:@[a-zA-Z0-9._-]+/)?[a-zA-Z0-9._-]+',name) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][a-zA-Z0-9.+-]+)?',version) or not entry.get('integrity'):
            raise ValueError('Legacy lockfile entry cannot be safely moved to the package gateway')
        entry['resolved']='https://registry.npmjs.org/'+name+'/-/'+name.rsplit('/',1)[-1]+'-'+version+'.tgz';changed=True
    if changed:
        backup=STATE/('lock-'+hashlib.sha256(original).hexdigest()+'.before-azure.json')
        if not backup.exists():backup.write_bytes(original);backup.chmod(0o600)
        # The original remains recoverable. Only resolved URLs change; package
        # versions, integrity hashes and dependency graphs remain identical.
        lock.write_text(json.dumps(data,indent=2)+'\n')

def main():
    with (STATE/'app.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if listening():return {'running':True,'reused':True}
        recipe=discover();cwd,argv=checked(recipe)
        RECIPE.parent.mkdir(exist_ok=True);RECIPE.write_text(json.dumps(recipe,indent=2))
        env={k:v for k,v in os.environ.items() if not k.endswith(('_TOKEN','_API_KEY'))}
        env.update(PORT='3000',HOST='0.0.0.0')
        restore_packages(cwd,argv,env)
        with (STATE/'app.log').open('ab') as log:
            child=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        for _ in range(240):
            if listening():return {'running':True,'reused':False}
            if child.poll() is not None:raise RuntimeError('App start failed; inspect ~/.local/state/lab/app.log and retry. No chat message is required.')
            time.sleep(.5)
        # Do not orphan a failed startup process group.
        os.killpg(child.pid,signal.SIGTERM)
        raise RuntimeError('App did not listen on port 3000 within two minutes.')
if __name__=='__main__':
    try:
        if len(sys.argv)>1:select_source(sys.argv[1])
        print(json.dumps(main()))
    except Exception as exc:print(json.dumps({'error':str(exc)}));sys.exit(1)
