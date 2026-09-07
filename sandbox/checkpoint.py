"""Bounded regular-file checkpoints inside quick pods. No symlinks or executable state."""
import base64,os,re,stat
from pathlib import Path,PurePosixPath
MAX_FILE=int(os.getenv('ARTIFACT_MAX_FILE_BYTES','8000000'))
MAX_TOTAL=int(os.getenv('ARTIFACT_MAX_TOTAL_BYTES','16000000'))
SKIP={'artifacts','plots','files','__pycache__','.venv','node_modules','.git'}
def valid(name):
    parts=PurePosixPath(name).parts
    return bool(parts) and len(parts)<=8 and len(name)<=400 and not name.startswith('/') and all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_. -]{0,159}',p) and '..' not in p for p in parts) and parts[0] not in SKIP

def restore(entries,root='/workspace'):
    if not isinstance(entries,list) or len(entries)>int(os.getenv('ARTIFACT_MAX_FILES','40')):raise ValueError('Invalid quick checkpoint')
    total=0
    for entry in entries:
        name=entry.get('name','')
        if not valid(name):raise ValueError('Invalid checkpoint path')
        raw=base64.b64decode(entry['data'],validate=True);total+=len(raw)
        if len(raw)>MAX_FILE or total>MAX_TOTAL:raise ValueError('Checkpoint limit exceeded')
        # Fresh clean pod; checkpoint paths cannot name symlinks or hidden config.
        p=Path(root)/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)

def collect_checkpoint(root='/workspace'):
    entries=[];total=0;truncated=False
    # fwalk + O_NOFOLLOW relative to the directory fd resists file/symlink swaps.
    for directory,dirs,files,fd in os.fwalk(root,follow_symlinks=False):
        relative=Path(directory).relative_to(root)
        dirs[:]=sorted(d for d in dirs if valid(str(relative/d)) and d not in SKIP)
        for name in sorted(files):
            key=str(relative/name)
            if not valid(key):continue
            try:
                handle=os.open(name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW,dir_fd=fd)
                with os.fdopen(handle,'rb') as f:
                    info=os.fstat(f.fileno())
                    if not stat.S_ISREG(info.st_mode):continue
                    if info.st_size>MAX_FILE or total+info.st_size>MAX_TOTAL or len(entries)>=int(os.getenv('ARTIFACT_MAX_FILES','40')):truncated=True;continue
                    raw=f.read(MAX_FILE+1)
                if len(raw)>MAX_FILE or total+len(raw)>MAX_TOTAL:truncated=True;continue
                entries.append({'name':key,'data':base64.b64encode(raw).decode()});total+=len(raw)
            except OSError:continue
    return {'files':entries,'truncated':truncated}
