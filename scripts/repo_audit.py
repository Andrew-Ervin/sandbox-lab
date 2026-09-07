"""Audit Git candidates/index without printing secrets; optionally export reviewed source."""
import argparse
import os
import re
import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {'.local', '.env', '.venv', '.runtime.nosync', 'node_modules', '.openai', '.terraform',
                 'conversations', 'artifacts', 'checkpoints', 'quick-checkpoints', 'user-apps', 'sessions'}
PRIVATE_SUFFIXES = ('.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx', '.vsix', '.log',
                    '.tfstate', '.tfvars', '.tfvars.json', '.kubeconfig', '.zip', '.tar', '.tgz', '.gz')
PATTERNS = {
    'temporary local experiment wiring (roll back before publishing)': re.compile(rb'(?m)^\s*(?:import live_bridge|from \.chat import live_bridge|from gui_setup import install)\b'),
    'provider credential': re.compile(rb'sk-or-v1-[0-9a-f]{48,}', re.I),
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'GitHub credential': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})'),
    'bearer capability': re.compile(rb'eyJ[A-Za-z0-9_-]{50,}\.[a-f0-9]{64}'),
    'cloud access key': re.compile(rb'\bAKIA[0-9A-Z]{16}\b'),
    'credential URL': re.compile(rb'https?://[^\s/<>"\x27:]+:[^\s/<>"\x27@]{8,}@'),
    'personal host path': re.compile(rb'/Users/[A-Za-z][A-Za-z0-9_.-]+/'),
}


def private_path(name):
    path = PurePosixPath(name)
    return (any(part in PRIVATE_PARTS for part in path.parts)
            or path.name.startswith('.env') and path.name != '.env.example'
            or name == 'docs/VERIFICATION.md'
            or path.name in ('kubeconfig', 'broker-kubeconfig')
            or bool(re.search(r'\.(?:tfstate|sqlite3?|db)(?:[.-].*)?$', path.name))
            or name.endswith(PRIVATE_SUFFIXES) and not name.endswith('.example.tfvars'))


def known_secrets(root):
    # Only the local environment is inspected; values NEVER appear in diagnostics.
    values = []
    env = root / '.env'
    if env.exists():
        for line in env.read_text().splitlines():
            name, sep, value = line.partition('=')
            value = value.strip().strip('\"\x27')
            if sep and re.search(r'(API_KEY|TOKEN_SECRET|PASSWORD)$', name.strip()) and len(value) >= 16:
                values.append(value.encode())
    return values


def findings(name, content, secrets=()):
    issues = []
    if private_path(name):
        issues.append((name, 0, 'private/generated path'))
    if len(content) > 5_000_000:
        issues.append((name, 0, 'large file needs explicit review'))
    for rule, pattern in PATTERNS.items():
        match = pattern.search(content)
        if match:
            issues.append((name, content[:match.start()].count(b'\n') + 1, rule))
    for value in secrets:
        index = content.find(value)
        if index >= 0:
            issues.append((name, content[:index].count(b'\n') + 1, 'local credential value'))
    return issues


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def candidates(root, staged):
    indexed = {}
    for row in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if not row: continue
        info, name = row.split(b'\t', 1)
        mode, oid, stage = info.decode().split()
        if stage != '0': raise RuntimeError('Resolve index conflicts before export')
        indexed[os.fsdecode(name)] = (mode, oid)
    names = set(indexed)
    if not staged:
        names.update(os.fsdecode(x) for x in git(root, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if x)
    for name in sorted(names):
        path = root / name
        if staged:
            mode, oid = indexed[name]
            if mode in ('100644','100755') and int(git(root,'cat-file','-s',oid)) > 5_000_000:
                mode='oversize'
            content = git(root, 'cat-file', 'blob', oid) if mode in ('100644', '100755') else b''
            yield name, content, mode
        elif path.exists() or path.is_symlink():
            is_link = path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root and root in p.parents)
            info=path.lstat()
            mode = '120000' if is_link else 'special' if not stat.S_ISREG(info.st_mode) else 'oversize' if info.st_size>5_000_000 else '100755' if info.st_mode & stat.S_IXUSR else '100644'
            yield name, path.read_bytes() if mode in ('100644','100755') else b'', mode


def audit(root, staged=False):
    files = list(candidates(root, staged))
    issues = []; secrets = known_secrets(root)
    for name, content, mode in files:
        if mode not in ('100644', '100755'):
            issues.append((name, 0, 'symlink, special, or oversized file requires review'))
        issues.extend(findings(name, content, secrets))
    return files, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Inspect exact index blobs, including forced ignored files')
    parser.add_argument('--archive', type=Path, help='Write a source-only ZIP after a successful audit')
    args = parser.parse_args()
    files, issues = audit(ROOT, args.staged)
    if issues:
        for name, line, reason in issues:
            print(f'{name}:{line}: {reason}')
        raise SystemExit(f'FAIL: {len(issues)} issue(s); no archive written. Matching values are intentionally hidden.')
    print(f'PASS: {len(files)} {"index" if args.staged else "source candidate"} files; no detected private paths or credentials.')
    if args.archive:
        destination = args.archive.resolve()
        if destination.is_relative_to(ROOT) and not destination.is_relative_to(ROOT / '.local'):
            raise SystemExit('Write exports outside the repository or under ignored .local/.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content, mode in files:
                entry = zipfile.ZipInfo('sandbox-lab/' + name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.external_attr = (int(mode, 8) << 16)
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, content)
        print('Source-only archive created: ' + str(destination))
    print('Review Git diff before pushing; this bounded scanner is not a complete DLP system.')


if __name__ == '__main__': main()
