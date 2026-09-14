"""Bounded, segmented private home transfer for compute replacement."""
import json
import gzip
import os
from pathlib import Path
import sys
import tarfile

CHUNK_BYTES=8_000_000
MAX_SOURCE_BYTES=4_000_000_000
MAX_ARCHIVE_BYTES=2_000_000_000

class Parts:
    def __init__(self,path):
        self.path=path;path.mkdir(mode=0o700);self.file=None;self.bytes=0;self.count=0;self.used=0
    def write(self,data):
        if self.bytes+len(data)>MAX_ARCHIVE_BYTES:raise ValueError('Compressed home exceeds the safe migration limit')
        length=len(data)
        while data:
            if self.file is None or self.used==CHUNK_BYTES:
                if self.file:self.file.close()
                self.file=(self.path/f'part-{self.count:04d}').open('xb');os.chmod(self.file.name,0o600)
                self.count+=1;self.used=0
            block=data[:CHUNK_BYTES-self.used];self.file.write(block)
            self.used+=len(block);self.bytes+=len(block);data=data[len(block):]
        return length
    def flush(self):
        if self.file:self.file.flush()
    def close(self):
        if self.file:self.file.close()


def pack(home,path):
    home=home.resolve();total=0;skipped=[]
    def safe(info):
        nonlocal total
        if info.isdev() or info.isfifo():return None
        if info.issym():
            resolved=((home/info.name).parent/info.linkname).resolve()
            if not resolved.is_relative_to(home):
                # This image-owned toolchain is recreated by project-init.sh.
                if info.name=='.rustup/toolchains/preinstalled' and resolved.is_relative_to(Path('/opt/rust-toolchains')):return None
                skipped.append(info.name);return None
            info.linkname=os.path.relpath(resolved,(home/info.name).parent)
        total+=info.size
        if total>MAX_SOURCE_BYTES:raise ValueError('Saved home exceeds the safe migration limit')
        return info
    writer=Parts(path)
    try:
        with gzip.GzipFile(fileobj=writer,mode='wb',compresslevel=1,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|') as archive:
                for child in home.iterdir():archive.add(child,arcname=child.name,filter=safe)
    finally:writer.close()
    return {'bytes':writer.bytes,'parts':writer.count,'source_bytes':total,'skipped_external_links':len(skipped)}


if __name__=='__main__':
    request=json.load(sys.stdin);path=Path(request['path'])
    if path.parent!=Path('/tmp') or not path.name.startswith('lab-home-') or not path.name.endswith('.parts'):raise ValueError('Invalid transfer path')
    print(json.dumps(pack(Path.home(),path)))
