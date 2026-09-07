"""Keep both localhost Coder forwards alive across pod or node restarts."""
import subprocess,time,signal
import urllib.request
import urllib.error
from pathlib import Path
root=Path(__file__).resolve().parents[1]
children={}; logs={}; stopped=False
failures={}; checked={}
def healthy(port):
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/v2/buildinfo',timeout=3) as response:
            return response.status==200
    except (OSError,urllib.error.URLError):return False
def stop(*_):
    global stopped
    stopped=True
signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
try:
    while not stopped:
        for ns,port in [('coder',7080),('coder-ai',7081)]:
            if ns in children and children[ns].poll() is None and time.monotonic()-checked.get(ns,0)>=10:
                checked[ns]=time.monotonic()
                failures[ns]=0 if healthy(port) else failures.get(ns,0)+1
                if failures[ns]>=2:
                    print(f'{ns}: stalled local connection; reconnecting',flush=True)
                    children[ns].terminate()
                    try:children[ns].wait(timeout=3)
                    except subprocess.TimeoutExpired:children[ns].kill();children[ns].wait()

            if ns not in children or children[ns].poll() is not None:
                failures[ns]=0;checked[ns]=time.monotonic()
                if ns in logs: logs[ns].close()
                logs[ns]=open(root/'.local'/f'{ns}-forward.log','a')
                children[ns]=subprocess.Popen(['kubectl','--kubeconfig',str(root/'.local/kubeconfig'),'-n',ns,'port-forward','--address','127.0.0.1','service/coder',f'{port}:7080'],stdout=logs[ns],stderr=subprocess.STDOUT)
        time.sleep(2)
finally:
    for p in children.values():
        if p.poll() is None: p.terminate()
    for p in children.values(): p.wait(timeout=10)
