"""Admin provisioning for the pinned Codex binary; never changes the package proxy.
Uses npm publication age and SHA-512 integrity, caps this one download at 250 MB.
"""
import argparse,base64,datetime,hashlib,json,subprocess,tempfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--pod',required=True);args=p.parse_args()
    command=['kubectl','--kubeconfig',str(ROOT/'.local/kubeconfig'),'-n','lab-dev','exec',args.pod,'--']
    machine=subprocess.check_output(command+['uname','-m'],text=True).strip()
    arch={'aarch64':'arm64','x86_64':'x64'}[machine];version='0.152.1-linux-'+arch
    with urllib.request.urlopen('https://registry.npmjs.org/@openai/codex',timeout=30) as r:metadata=json.load(r)
    published=datetime.datetime.fromisoformat(metadata['time'][version].replace('Z','+00:00'))
    if datetime.datetime.now(datetime.timezone.utc)-published<datetime.timedelta(days=5):raise RuntimeError('Release is too new')
    dist=metadata['versions'][version]['dist']
    if not dist['tarball'].startswith('https://registry.npmjs.org/@openai/codex/-/'):raise RuntimeError('Unexpected registry URL')
    with urllib.request.urlopen(dist['tarball'],timeout=60) as r:data=r.read(250_000_001)
    if len(data)>250_000_000:raise RuntimeError('CLI archive exceeds provisioning limit')
    expected='sha512-'+base64.b64encode(hashlib.sha512(data).digest()).decode()
    if dist['integrity']!=expected:raise RuntimeError('Integrity mismatch')
    target='/home/sandbox/.local/share/lab-harnesses/node_modules/@openai/codex-linux-'+arch
    # Extract regular files only, confined to the named package directory.
    extract='''import io,tarfile,pathlib,sys
root=pathlib.Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode="r:gz") as archive:
 for entry in archive:
  if not entry.isfile():continue
  relative=pathlib.PurePosixPath(entry.name)
  if relative.parts[0]!="package" or ".." in relative.parts:raise RuntimeError("Invalid archive path")
  path=root.joinpath(*relative.parts[1:]);path.parent.mkdir(parents=True,exist_ok=True)
  path.write_bytes(archive.extractfile(entry).read());path.chmod(entry.mode & 0o755)
'''
    subprocess.run(command[:-1]+['-i','--','python','-c',extract,target],input=data,check=True)
    print('Provisioned verified Codex '+version+'; shared package proxy unchanged.')
if __name__=='__main__':main()
