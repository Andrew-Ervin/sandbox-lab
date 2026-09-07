"""Verified tool bootstrap for macOS/Linux; Windows uses WSL2, not native Python."""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def target(system=None, machine=None):
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    if system == 'windows':
        raise ValueError('Use Ubuntu in WSL2 with Linux containers. Run the setup inside WSL, not PowerShell/Python for Windows.')
    if system not in ('linux', 'darwin') or machine not in ('arm64', 'aarch64', 'x86_64', 'amd64'):
        raise ValueError('Supported hosts: macOS/Linux AMD64 or ARM64 (glibc Linux, including WSL2).')
    return system, 'arm64' if machine in ('arm64', 'aarch64') else 'amd64'


def plan(system, arch):
    triple = ('aarch64' if arch == 'arm64' else 'x86_64') + ('-apple-darwin' if system == 'darwin' else '-unknown-linux-gnu')
    return {
        'kind': 'kind-' + system + '-' + arch,
        'coder': 'coder_2.36.4_' + system + '_' + arch + ('.zip' if system == 'darwin' else '.tar.gz'),
        'uv': 'uv-' + triple + '.tar.gz',
        'ori': 'ori-linux-' + ('arm64' if arch == 'arm64' else 'x64'),
        'code-server': 'code-server-4.106.3-linux-' + arch + '.tar.gz',
        'calico': 'calico.yaml',
    }


def unpack_file(archive, basename, output):
    # Extract one regular file, never archive paths/symlinks or arbitrary member trees.
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as z:
            member = next(x for x in z.infolist() if Path(x.filename).name == basename and not x.is_dir())
            output.write_bytes(z.read(member))
    else:
        with tarfile.open(archive, 'r:gz') as tar:
            member = next(x for x in tar.getmembers() if Path(x.name).name == basename and x.isfile())
            with tar.extractfile(member) as source, output.open('wb') as dest:
                shutil.copyfileobj(source, dest)
    output.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--system', choices=['linux', 'darwin'], help='Dry-run target only')
    parser.add_argument('--arch', choices=['amd64', 'arm64'], help='Dry-run target only')
    args = parser.parse_args()
    if (args.system or args.arch) and not args.dry_run:
        parser.error('Cross-target overrides are only supported with --dry-run; build on the target architecture.')
    system, arch = target(args.system, args.arch)
    assets = plan(system, arch)
    lock = json.loads((ROOT / 'scripts/tool-downloads.lock.json').read_text())
    if args.dry_run:
        print(json.dumps({'system': system, 'arch': arch, 'assets': assets}, indent=2))
        assert all(a in lock for a in assets.values())
        return
    bins = ROOT / '.local/bin'; bins.mkdir(parents=True, exist_ok=True)
    cache = ROOT / '.local/research'; cache.mkdir(parents=True, exist_ok=True)
    for name, asset in assets.items():
        entry = lock[asset]; path = cache / asset
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            print('Downloading ' + asset, flush=True)
            temporary = path.with_suffix(path.suffix + '.download')
            with urllib.request.urlopen(entry['url'], timeout=120) as source, temporary.open('wb') as dest:
                shutil.copyfileobj(source, dest)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != entry['sha256']:
                temporary.unlink()
                raise RuntimeError('Checksum mismatch: ' + asset)
            temporary.replace(path)
        if name in ('coder', 'uv'):
            unpack_file(path, name, bins / name)
        elif name == 'kind':
            shutil.copyfile(path, bins / name); (bins / name).chmod(0o755)
        elif name == 'ori':
            shutil.copyfile(path, bins / ('ori-linux-' + arch)); (bins / ('ori-linux-' + arch)).chmod(0o755)
        elif name == 'code-server':
            shutil.copyfile(path, bins / ('code-server-linux-' + arch + '.tar.gz'))
    venv = ROOT / '.venv'
    if not venv.exists():
        if system == 'darwin':
            destination = ROOT / '.runtime.nosync/python'
            destination.parent.mkdir(exist_ok=True)
        else:
            destination = venv
        subprocess.run([str(bins / 'uv'), 'venv', '--python', '3.12', str(destination)], check=True)
        if destination != venv:
            venv.symlink_to(destination.relative_to(ROOT), target_is_directory=True)
    print('Verified tools ready. Existing environments were preserved. Next: bash scripts/setup.sh')


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        raise SystemExit(str(error))
