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
        for name in sorted(os.listdir(root_fd))[:40]:
            if '/' in name or name.startswith('.') or len(name) > 160:
                continue
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 8_000_000 or total + info.st_size > 16_000_000:
                        continue
                    data = os.read(fd, 8_000_001)
                    if len(data) > 8_000_000 or total + len(data) > 16_000_000: continue
                    total += len(data)
                    found.append({'name':name,'data':base64.b64encode(data).decode()})
                finally: os.close(fd)
            except OSError: continue
    finally: os.close(root_fd)
    return found
if __name__ == '__main__': print(json.dumps(collect()))
