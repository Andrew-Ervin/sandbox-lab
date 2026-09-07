"""Return bounded regular artifacts; never follow symlinks from untrusted code."""
import base64, json, os, stat
from pathlib import Path
ROOT = Path('/workspace/artifacts')

def collect():
    found = []
    total = 0
    try:
        root_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return found
    try:
        # Avoid allocating a list for an unbounded directory produced by code.
        names=[]
        with os.scandir(root_fd) as scan:
            for entry in scan:
                names.append(entry.name)
                if len(names)>=10000:break
        for name in sorted(names)[:int(os.getenv('ARTIFACT_MAX_FILES','40'))]:
            if '/' in name or name.startswith('.') or len(name) > 160:
                continue
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_size > int(os.getenv('ARTIFACT_MAX_FILE_BYTES','8000000')) or total + info.st_size > int(os.getenv('ARTIFACT_MAX_TOTAL_BYTES','16000000')):
                        continue
                    data = os.read(fd, int(os.getenv('ARTIFACT_MAX_FILE_BYTES','8000000'))+1)
                    if len(data) > int(os.getenv('ARTIFACT_MAX_FILE_BYTES','8000000')) or total + len(data) > int(os.getenv('ARTIFACT_MAX_TOTAL_BYTES','16000000')): continue
                    total += len(data)
                    found.append({'name':name,'data':base64.b64encode(data).decode()})
                finally: os.close(fd)
            except OSError: continue
    finally: os.close(root_fd)
    return found
if __name__ == '__main__': print(json.dumps(collect()))
