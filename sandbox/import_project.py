"""Publish an explicit source snapshot in an inbox. Never overwrite live files."""
import base64,hashlib,json,os,re,shutil,sys,uuid
ROOT='/home/sandbox/project'

def directory(parent,name,create=False):
    if create:
        try:os.mkdir(name,0o700,dir_fd=parent)
        except FileExistsError:pass
    return os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)

def publish(request,root_path=ROOT):
    key=request['id']
    if not re.fullmatch(r'transfer_[a-f0-9]{32}',key):raise ValueError('Invalid transfer')
    entries=request['files']
    if not isinstance(entries,list) or len(entries)>int(os.getenv('SYNC_MAX_FILES','2000')):raise ValueError('Too many files')
    files=[];seen=set();total=0
    for entry in entries:
        path=entry['path'];parts=path.split('/')
        if len(path)>1024 or len(parts)>16 or any(not n or n in ('.','..') or '\\' in n or '\x00' in n or (n.startswith('.') and n!='.lab') or n in ('node_modules','venv','target','__pycache__') or n.lower().endswith(('.pem','.key','.p12','.pfx')) for n in parts):raise ValueError('Excluded path')
        if path in seen or path.startswith('.lab/imports/'):raise ValueError('Duplicate or recursive import')
        raw=base64.b64decode(entry['data'],validate=True);total+=len(raw)
        if len(raw)>int(os.getenv('SYNC_MAX_FILE_BYTES','8000000')) or total>int(os.getenv('SYNC_MAX_TOTAL_BYTES','32000000')):raise ValueError('Import exceeds size limit')
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Import checksum mismatch')
        seen.add(path);files.append((parts,raw))
    root=os.open('/',os.O_RDONLY|os.O_DIRECTORY);inbox=None;stage=None
    try:
        for name in root_path.strip('/').split('/'):
            fd=directory(root,name);os.close(root);root=fd
        lab=directory(root,'.lab',True)
        try:inbox=directory(lab,'imports',True)
        finally:os.close(lab)
        try:existing=directory(inbox,key)
        except FileNotFoundError:pass
        else:
            os.close(existing)
            if request.get('reuse') is True:
                return {'path':'.lab/imports/'+key,'file_count':len(files),'bytes':total,'reused':True}
            raise ValueError('Transfer already exists')
        count=0
        with os.scandir(inbox) as scan:
            for n,entry in enumerate(scan):
                if n>=100:raise ValueError('Import inbox needs cleanup')
                if re.fullmatch(r'transfer_[a-f0-9]{32}',entry.name):count+=1
        if count>=int(os.getenv('SYNC_MAX_IMPORTS','3')):raise ValueError('Move or remove an earlier import first; three snapshots are retained at most')
        try:os.stat(key,dir_fd=inbox,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise ValueError('Transfer already exists')
        stage='.pending-'+uuid.uuid4().hex;os.mkdir(stage,0o700,dir_fd=inbox)
        staged=directory(inbox,stage)
        try:
            for parts,raw in files:
                parent=os.dup(staged)
                try:
                    for name in parts[:-1]:
                        fd=directory(parent,name,True);os.close(parent);parent=fd
                    fd=os.open(parts[-1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
                    with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
                finally:os.close(parent)
        finally:os.close(staged)
        os.rename(stage,key,src_dir_fd=inbox,dst_dir_fd=inbox);stage=None;os.fsync(inbox)
        return {'path':'.lab/imports/'+key,'file_count':len(files),'bytes':total}
    finally:
        if stage and inbox is not None:shutil.rmtree(stage,dir_fd=inbox)
        if inbox is not None:os.close(inbox)
        os.close(root)

if __name__=='__main__':
    try:print(json.dumps(publish(json.load(sys.stdin))))
    except (OSError,ValueError,KeyError):print(json.dumps({'error':'Import could not be published. Check the inbox limit, file paths and checksums.'}));sys.exit(1)
