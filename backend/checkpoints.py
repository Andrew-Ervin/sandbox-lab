"""Local conversation file snapshots, independent of disposable compute lifetime."""
import base64,hashlib,json,re
from pathlib import PurePosixPath
from .config import STATE

def directory(thread_id):return STATE/'quick-checkpoints'/hashlib.sha256(thread_id.encode()).hexdigest()
def validate(entries):
    if not isinstance(entries,list) or len(entries)>40:raise ValueError('Invalid quick checkpoint')
    total=0;seen=set()
    for entry in entries:
        name=entry.get('name','');parts=PurePosixPath(name).parts
        if not parts or name.startswith('/') or len(parts)>8 or len(name)>400 or name in seen or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_. -]{0,159}',p) or '..' in p for p in parts) or parts[0] in {'artifacts','plots','files','__pycache__','.venv','node_modules','.git'}:raise ValueError('Invalid checkpoint path')
        raw=base64.b64decode(entry.get('data',''),validate=True);total+=len(raw);seen.add(name)
        if len(raw)>8_000_000 or total>16_000_000:raise ValueError('Quick checkpoint exceeds file limits')
    return entries

def save(thread_id,run_id,value):
    entries=validate(value.get('files',[]));folder=directory(thread_id);folder.mkdir(parents=True,exist_ok=True)
    target=folder/'latest.json';temp=folder/'latest.tmp'
    temp.write_text(json.dumps({'run_id':run_id,'files':entries,'truncated':bool(value.get('truncated'))}));temp.chmod(0o600);temp.replace(target)
    return {'files':len(entries),'truncated':bool(value.get('truncated'))}

def load(thread_id):
    path=directory(thread_id)/'latest.json'
    if not path.exists():return []
    if path.is_symlink() or path.stat().st_size>23_000_000:raise ValueError('Invalid saved checkpoint')
    return validate(json.loads(path.read_text()).get('files',[]))
