"""Fetch only the checksum-pinned official Open VSX packages in the reviewed lock."""
import hashlib
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

root=Path(__file__).resolve().parents[1]
cache=root/'.local/azure-pilot/extensions';cache.mkdir(parents=True,exist_ok=True)
for entry in json.loads((root/'infra/editor-extensions.lock.json').read_text())['extensions']:
    if datetime.fromisoformat(entry['published'].replace('Z','+00:00'))>datetime.now(timezone.utc)-timedelta(days=5):raise RuntimeError('Extension release is too recent')
    path=cache/entry['file']
    if path.exists():
        with path.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()==entry['sha256']:continue
    temp=path.with_suffix('.download')
    with urllib.request.urlopen(entry['url'],timeout=120) as response,temp.open('wb') as dest:
        size=0
        while chunk:=response.read(1024*1024):
            size+=len(chunk)
            if size>250_000_000:raise RuntimeError('Extension exceeds reviewed artifact size')
            dest.write(chunk)
    with temp.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=entry['sha256']:raise RuntimeError('Extension checksum mismatch')
    temp.replace(path)
