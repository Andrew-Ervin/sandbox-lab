"""Read-only source browser/export. Never follows symlinks or executes project code."""
import os,stat,json,sys,base64
ROOT='/home/sandbox/project'
DEPENDENCIES={'node_modules','.venv','venv','__pycache__','.git','.cache','target'}
GENERATED={'dist','build','bin','obj'}
MAX_FILE=8_000_000
MAX_TOTAL=32_000_000
MAX_FILES=2000
MAX_ENTRIES=10000

def bounded_names(fd,limit):
    # Bound allocation before sorting, including excluded names in the budget.
    names=[]
    with os.scandir(fd) as scan:
        for entry in scan:
            if len(names)>=limit:raise ValueError('Project export contains too many entries; narrow the project contents')
            names.append(entry.name)
    return sorted(names)

def parts(path):
    if not isinstance(path,str) or len(path)>1024 or path.startswith('/') or '\\' in path:raise ValueError('Invalid project path')
    values=path.split('/') if path else []
    if len(values)>16 or any(v in ('','.', '..') or '\x00' in v for v in values):raise ValueError('Invalid project path')
    return values

def visible(name):
    return name not in DEPENDENCIES and (not name.startswith('.') or name=='.lab') and not name.lower().endswith(('.pem','.key','.p12','.pfx'))

def open_path(root,path,directory=False):
    names=parts(path)
    if any(not visible(n) for n in names):raise ValueError('Dependency and credential paths are excluded')
    fd=os.dup(root)
    try:
        for index,name in enumerate(names):
            flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
            if index<len(names)-1 or directory:flags|=os.O_DIRECTORY
            nextfd=os.open(name,flags,dir_fd=fd);os.close(fd);fd=nextfd
        mode=os.fstat(fd).st_mode
        if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):raise ValueError('Unsupported file type')
        return fd
    except BaseException:os.close(fd);raise

def read_file(root,path):
    fd=open_path(root,path)
    try:
        if os.fstat(fd).st_size>MAX_FILE:raise ValueError('File exceeds the 8 MB preview/sync limit')
        chunks=[];size=0
        while chunk:=os.read(fd,min(65536,MAX_FILE+1-size)):
            size+=len(chunk)
            if size>MAX_FILE:raise ValueError('File exceeds the 8 MB preview/sync limit')
            chunks.append(chunk)
        return b''.join(chunks)
    finally:os.close(fd)

def execute(request,root_path=ROOT):
    # Open every fixed root component without following a replaced project symlink.
    root=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for name in root_path.strip('/').split('/'):
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root);os.close(root);root=fd
        action=request['action'];path=request.get('path','');parts(path)
        if action=='list':
            fd=open_path(root,path,True)
            try:
                entries=[];hidden=0;truncated=False
                with os.scandir(fd) as scan:
                    for visited,entry in enumerate(scan):
                        if visited>=MAX_ENTRIES or len(entries)>=MAX_FILES:truncated=True;break
                        name=entry.name
                        if not visible(name):hidden+=1;continue
                        try:st=entry.stat(follow_symlinks=False)
                        except FileNotFoundError:hidden+=1;continue  # A build may remove an entry while browsing.
                        if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):hidden+=1;continue
                        entries.append({'name':name,'path':path+'/'+name if path else name,'directory':stat.S_ISDIR(st.st_mode),'size':st.st_size if stat.S_ISREG(st.st_mode) else 0})
                entries.sort(key=lambda entry:entry['name'])
                return {'path':path,'entries':entries,'excluded':hidden,'limit':MAX_FILES,'truncated':truncated}
            finally:os.close(fd)
        if action=='read':
            raw=read_file(root,path)
            return {'path':path,'data':base64.b64encode(raw).decode(),'size':len(raw)}
        if action=='export':
            base=path
            files=[];skipped=0;size=0;visited=0
            def walk(path):
                nonlocal skipped,size,visited
                fd=open_path(root,path,True)
                try:
                    names=bounded_names(fd,MAX_ENTRIES-visited);visited+=len(names)
                    for name in names:
                        if not visible(name) or name in GENERATED:skipped+=1;continue
                        entry=path+'/'+name if path else name
                        relative=entry[len(base)+1:] if base else entry
                        if relative=='.lab/imports':skipped+=1;continue
                        st=os.stat(name,dir_fd=fd,follow_symlinks=False)
                        if stat.S_ISDIR(st.st_mode):walk(entry)
                        elif stat.S_ISREG(st.st_mode):
                            if st.st_size>MAX_FILE:skipped+=1;continue
                            raw=read_file(root,entry)
                            if len(files)>=MAX_FILES or size+len(raw)>MAX_TOTAL:raise ValueError('Mock sync exceeds 2,000 files or 32 MB; previous copy was retained')
                            size+=len(raw);files.append({'path':relative,'data':base64.b64encode(raw).decode()})
                        else:skipped+=1
                finally:os.close(fd)
            walk(base)
            return {'files':files,'excluded':skipped,'bytes':size}
        raise ValueError('Unknown project operation')
    finally:os.close(root)

if __name__=='__main__':
    try:print(json.dumps(execute(json.load(sys.stdin))))
    except (OSError,ValueError,KeyError):print(json.dumps({'error':'Project path is unavailable, excluded, or exceeds the browser/sync limits.'}));sys.exit(1)
