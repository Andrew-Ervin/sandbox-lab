"""Fixed token-only update, sent by the trusted host; no workspace-supplied code."""
import json,os,sys,tempfile
from pathlib import Path

def rotate(data,home=None):
    folder=(home or Path.home())/'.config/lab'
    if not folder.is_dir() or not (folder/'token').is_file():raise ValueError('Workspace model setup is required')
    for name,value in [('token',data['token']),('capability.json',json.dumps({'expires':data['expires'],'model':data['model']}))]:
        fd,temp=tempfile.mkstemp(prefix='.renew-',dir=folder)
        try:
            with os.fdopen(fd,'w') as f:f.write(value);f.flush();os.fsync(f.fileno())
            os.replace(temp,folder/name)
        finally:
            if os.path.exists(temp):os.unlink(temp)
    return {'expires':data['expires']}

if __name__=='__main__':
    try:print(json.dumps(rotate(json.load(sys.stdin))))
    except Exception:
        print(json.dumps({'error':'Workspace credential renewal failed'}));sys.exit(1)
