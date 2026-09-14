"""Root-owned supervisor: execute one bounded request as uid 1000, never root."""
import ctypes
import fcntl
import time
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile


def execute(request):
    timeout = min(1800, max(1, int(request.get('timeout', 60))))
    maximum = min(70_000_000, max(1024, int(request.get('maximum', 1_000_000))))
    env = {'HOME': '/home/sandbox', 'USER': 'sandbox', 'LOGNAME': 'sandbox',
           'PATH': '/home/sandbox/.local/bin:/opt/lab/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/go/bin:/usr/share/dotnet:/usr/local/cargo/bin:/usr/local/julia/bin',
           'LANG': 'C.UTF-8', 'PYTHONUNBUFFERED': '1', 'PYTHONPATH': '/opt/lab',
           'UV_INDEX_URL': 'http://127.0.0.1:3128/python/simple/', 'UV_INSECURE_HOST': '127.0.0.1',
           'JULIA_PKG_SERVER': 'http://127.0.0.1:3128/julia', 'DOTNET_CLI_TELEMETRY_OPTOUT': '1',
           'CARGO_HOME':'/home/sandbox/.cargo','RUSTUP_HOME':'/home/sandbox/.rustup','GOPATH':'/home/sandbox/go',
           'DOTNET_ROOT':'/usr/share/dotnet','DOTNET_CLI_HOME':'/home/sandbox','NUGET_PACKAGES':'/home/sandbox/.nuget/packages',
           'JULIA_DEPOT_PATH':'/home/sandbox/.julia','MPLCONFIGDIR':'/tmp/matplotlib','NUMBA_CACHE_DIR':'/tmp/numba',
           'BROWSER_PATH':'/opt/lab/chromium-for-plots','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    env['npm_config_cache'] = '/home/sandbox/.cache/lab-npm'
    env['LAB_AZURE_RUNTIME'] = '1'
    env.update(PI_TELEMETRY='0', ORI_TELEMETRY='0', ORI_NO_UPDATE_CHECK='1', DOTNET_NOLOGO='1')
    for name, val in request.get('limits', {}).items():
        if name.startswith(('SYNC_', 'ARTIFACT_', 'QUICK_', 'APP_PACKAGE_RESTORE_')): env[name] = str(val)
    def restrict():
        os.setgroups([]); os.setgid(1000); os.setuid(1000)
        if ctypes.CDLL(None).prctl(38, 1, 0, 0, 0) != 0: os._exit(125)  # no_new_privs
        resource.setrlimit(resource.RLIMIT_NOFILE, (2048, 2048))
        # Captured output and workspace files have different limits. Native
        # package binaries must not inherit a one-megabyte stdout truncation
        # setting. Quick user code applies its existing eight-megabyte limit
        # again in quick.py; the Azure root disk bounds total workspace storage.
        file_limit = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(request['argv'], cwd=request.get('cwd', '/home/sandbox/project'),
                                env=env, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                start_new_session=True, preexec_fn=restrict)
        timed_out = False
        try: proc.communicate(request.get('stdin', '').encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True; os.killpg(proc.pid, signal.SIGKILL); proc.wait()
        out.seek(0); err.seek(0)
        return {'stdout': out.read(maximum).decode(errors='replace'), 'stderr': err.read(min(maximum, 32000)).decode(errors='replace'),
                'exit_code': proc.returncode, 'timed_out': timed_out}


def reconcile(folder, now=None):
    """Reclaim abandoned operations, but never files owned by a live supervisor."""
    now = time.time() if now is None else now
    for path in list(folder.glob('*.request'))+list(folder.glob('*.result'))+list(folder.glob('*.tmp')):
        ident=path.stem
        if len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):continue
        try:
            if path.stat().st_mtime > now-3600:continue
        except FileNotFoundError:continue
        with (folder/(ident+'.lock')).open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:continue
            for suffix in ('request','result','tmp'):
                (folder/(ident+'.'+suffix)).unlink(missing_ok=True)
        (folder/(ident+'.lock')).unlink(missing_ok=True)


def supervise(ident, folder):
    reconcile(folder)
    with (folder/(ident+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        request = json.loads((folder / (ident+'.request')).read_text())
        try: result = execute(request)
        except Exception: result = {'exit_code': 125, 'stdout': '', 'stderr': 'Sandbox supervisor failed'}
        temp = folder / (ident+'.tmp'); temp.write_text(json.dumps(result)); temp.replace(folder / (ident+'.result'))
    (folder/(ident+'.lock')).unlink(missing_ok=True)


if __name__ == '__main__':
    ident = sys.argv[1]
    if len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident): raise ValueError('Invalid operation')
    supervise(ident, Path('/var/lib/lab/requests'))
