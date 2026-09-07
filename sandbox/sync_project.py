"""Apply bounded source changes with expected hashes; never follow symlinks."""
import base64,hashlib,json,os,re,stat,sys,uuid

EXCLUDED={'node_modules','venv','target','__pycache__','dist','build','bin','obj'}
def parts(path):
    if not isinstance(path,str) or len(path)>1024:raise ValueError('Invalid path')
    names=path.split('/')
    if len(names)>16 or any(not n or n in ('.','..') or '\\' in n or '\x00' in n or (n.startswith('.') and n!='.lab') or n in EXCLUDED or n.lower().endswith(('.pem','.key','.p12','.pfx')) for n in names):raise ValueError('Excluded path')
    if path.startswith('.lab/imports/'):raise ValueError('Recursive source copy')
    return names

def digest(parent,name):
    try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    except FileNotFoundError:return None
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>int(os.getenv('SYNC_MAX_FILE_BYTES','8000000')):raise ValueError('Unsupported destination')
        h=hashlib.sha256();total=0
        while chunk:=os.read(fd,65536):
            total+=len(chunk)
            if total>int(os.getenv('SYNC_MAX_FILE_BYTES','8000000')):raise ValueError('Growing destination')
            h.update(chunk)
        return h.hexdigest()
    finally:os.close(fd)

def apply(request,root_path='/home/sandbox/project'):
    scope=request.get('scope','')
    if scope and not re.fullmatch(r'\.lab/imports/transfer_[a-f0-9]{32}',scope):raise ValueError('Invalid source folder')
    changes=request['changes'];total=0;checked=[];seen=set()
    if not isinstance(changes,list) or len(changes)>int(os.getenv('SYNC_MAX_FILES','2000')):raise ValueError('Too many changes')
    for change in changes:
        names=parts(change['path']);before=change['before'];data=change['data']
        if before is not None and not re.fullmatch('[a-f0-9]{64}',before):raise ValueError('Invalid expected hash')
        if change['path'] in seen:raise ValueError('Duplicate change')
        seen.add(change['path'])
        raw=base64.b64decode(data,validate=True) if data is not None else None
        if raw is not None:
            total+=len(raw)
            if len(raw)>int(os.getenv('SYNC_MAX_FILE_BYTES','8000000')) or total>int(os.getenv('SYNC_MAX_TOTAL_BYTES','32000000')):raise ValueError('Change too large')
        mode=change.get('mode',0o600)
        if type(mode) is not int:raise ValueError('Invalid file mode')
        checked.append((change['path'],names,before,raw,0o600|(mode&0o100)))
    root=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    applied=[];conflicts=[]
    try:
        for name in (root_path+('/'+scope if scope else '')).strip('/').split('/'):
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root);os.close(root);root=fd
        for path,names,before,raw,mode in checked:
            parent=os.dup(root);temporary=None
            try:
                for name in names[:-1]:
                    if raw is not None:
                        try:os.mkdir(name,0o700,dir_fd=parent)
                        except FileExistsError:pass
                    fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=fd
                if digest(parent,names[-1])!=before:conflicts.append(path);continue
                if raw is None:
                    if before is not None:os.unlink(names[-1],dir_fd=parent)
                else:
                    temporary='.sync-'+uuid.uuid4().hex
                    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
                    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fchmod(stream.fileno(),mode);os.fsync(stream.fileno())
                    if digest(parent,names[-1])!=before:conflicts.append(path);continue
                    os.replace(temporary,names[-1],src_dir_fd=parent,dst_dir_fd=parent);temporary=None
                os.fsync(parent);applied.append(path)
            except (OSError,ValueError):conflicts.append(path)
            finally:
                if temporary:
                    try:os.unlink(temporary,dir_fd=parent)
                    except FileNotFoundError:pass
                os.close(parent)
        return {'applied':applied,'conflicts':conflicts}
    finally:os.close(root)

if __name__=='__main__':
    try:print(json.dumps(apply(json.load(sys.stdin))))
    except (OSError,ValueError,KeyError):print(json.dumps({'error':'Source sync rejected an unsafe or oversized change.'}));sys.exit(1)
