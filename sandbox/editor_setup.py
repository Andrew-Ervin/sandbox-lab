"""Launch the existing editor with the approved local extension gallery."""
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

GALLERY={'serviceUrl':'http://127.0.0.1:3128/vscode/gallery'}


def launch(executable):
    changed=False
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if proc.stat().st_uid!=os.getuid():continue
            args=(proc/'cmdline').read_bytes().decode().split('\0')
            if len(args)<2 or not args[1].endswith('/out/node/entry'):continue
            if not args[1].startswith(('/opt/code-server-','/opt/lab/ide/code-server-','/usr/lib/code-server/')):continue
            env=dict(e.split('=',1) for e in (proc/'environ').read_bytes().decode().split('\0') if '=' in e)
            if json.loads(env.get('EXTENSIONS_GALLERY','{}'))!=GALLERY:
                os.kill(int(proc.name),signal.SIGTERM);changed=True
        except (OSError,UnicodeError,ValueError):continue
    for _ in range(30 if changed else 1):
        try:
            sock=socket.create_connection(('127.0.0.1',13337),timeout=.2);sock.close()
            if not changed:return
        except OSError:break
        time.sleep(.1)
    else:raise RuntimeError('The old editor is still stopping; files are retained')
    env={**os.environ,'EXTENSIONS_GALLERY':json.dumps(GALLERY)}
    with open('/home/sandbox/.code-server.log','ab') as log:
        subprocess.Popen([executable,'--bind-addr','127.0.0.1:13337','--auth','none','--disable-telemetry','--disable-update-check','/home/sandbox/project'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
