"""Run trusted local services; Ctrl-C stops them, leaving Kubernetes workspaces intact."""
import os,signal,subprocess,time
from pathlib import Path
if os.name=='nt': raise SystemExit('Run the launcher in Ubuntu/WSL2; native Windows processes are not supported. See docs/LOCAL-SETUP.md')
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
LOCAL=ROOT/'.local'; LOCAL.mkdir(exist_ok=True)
PYTHON=str(ROOT/'.venv/bin/python')
commands={'coder-connections':[PYTHON,'scripts/forward_coder.py'],'backend':[PYTHON,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8787','--no-access-log'],'frontend':['npm','run','dev','--','--host','127.0.0.1','--port','3000']}
children={}; logs={}; stop=False

def end(*_):
    global stop
    stop=True
signal.signal(signal.SIGINT,end); signal.signal(signal.SIGTERM,end)
try:
    print('Chat: http://127.0.0.1:3000\nDeveloper portal: http://127.0.0.1:7080\nAI Coder portal: http://127.0.0.1:7081',flush=True)
    for name,command in commands.items():
        logs[name]=open(LOCAL/f'{name}.log','ab')
        children[name]=subprocess.Popen(command,stdout=logs[name],stderr=subprocess.STDOUT,start_new_session=True)
    while not stop:
        for name,child in children.items():
            if child.poll() is not None:
                print(f'{name} exited; see .local/{name}.log',flush=True); stop=True
        time.sleep(1)
finally:
    for child in children.values():
        if child.poll() is None: os.killpg(child.pid,signal.SIGTERM)
    for child in children.values():
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL)
    for log in logs.values(): log.close()
