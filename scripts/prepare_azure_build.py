"""Prepare an explicit source-only ACR build context; never upload the workspace."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT/'.local/azure-pilot/build-context'
    if target.exists(): shutil.rmtree(target)
    target.mkdir(parents=True,mode=0o700)
    manifest = []
    sources = [p for p in (ROOT/'sandbox').rglob('*') if p.is_file() and not p.is_symlink()
               and not any(x in ('__pycache__','.pytest_cache','node_modules','.git','.venv') for x in p.parts)]
    sources.append(ROOT/'.dockerignore')
    lock = json.loads((ROOT/'scripts/tool-downloads.lock.json').read_text())
    for name,asset in [('ori-linux-amd64','ori-linux-x64'),('code-server-linux-amd64.tar.gz','code-server-4.106.3-linux-amd64.tar.gz')]:
        p = ROOT/'.local/bin'/name
        if hashlib.sha256(p.read_bytes()).hexdigest() != lock[asset]['sha256']: raise RuntimeError('Tool checksum mismatch')
        sources.append(p)
    for source in sorted(sources):
        relative = source.relative_to(ROOT)
        if any(x in ('.env','credentials','conversations','workspaces') for x in relative.parts): raise RuntimeError('Private path in build context')
        dest = target/relative; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,dest)
        manifest.append({'path':str(relative),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'bytes':dest.stat().st_size})
    (target.parent/'build-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'context':str(target),'files':len(manifest),'bytes':sum(x['bytes'] for x in manifest),'only_sandbox_source_and_two_verified_tools':True}))


if __name__ == '__main__': main()
