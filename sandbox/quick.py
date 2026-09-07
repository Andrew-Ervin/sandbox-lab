"""This supervisor and the generated program live inside a disposable pod."""
import json, os, resource, signal, subprocess, sys, tempfile, base64, re, time
from pathlib import Path
from collect import collect
from checkpoint import restore,collect_checkpoint
request = json.load(sys.stdin)
code = request['code']
if not isinstance(code, str) or len(code) > int(os.getenv('QUICK_CODE_CHARS','100000')): raise ValueError('Invalid code size')
Path('/workspace/artifacts').mkdir(exist_ok=True)
Path('/workspace/files').mkdir(exist_ok=True)
total=0
for entry in request.get('files',[])[:int(os.getenv('ARTIFACT_MAX_FILES','40'))]:
    name=entry['name']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_. -]{0,159}',name) or '..' in name: raise ValueError('Invalid input file')
    raw=base64.b64decode(entry['data'],validate=True); total+=len(raw)
    if len(raw)>int(os.getenv('ARTIFACT_MAX_FILE_BYTES','8000000')) or total>int(os.getenv('ARTIFACT_MAX_TOTAL_BYTES','16000000')): raise ValueError('Input limit exceeded')
    (Path('/workspace/files')/name).write_bytes(raw)
restore(request.get('checkpoint',[]))
Path('/workspace/main.py').write_text(code)
def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (int(os.getenv('QUICK_CPU_SECONDS','25')),)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (int(os.getenv('ARTIFACT_MAX_FILE_BYTES','8000000')), int(os.getenv('ARTIFACT_MAX_FILE_BYTES','8000000'))))
    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
with tempfile.TemporaryFile() as out:
    started=time.monotonic()
    launcher='/opt/lab/plot_capture.py' if 'plotly' in code else '/workspace/main.py'
    process = subprocess.Popen([sys.executable,launcher], stdout=out, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
    timed_out = False
    try: process.wait(timeout=int(os.getenv('QUICK_RUN_SECONDS','30')))
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    out.seek(0)
    output = out.read(int(os.getenv('QUICK_STDOUT_BYTES','64000'))).decode(errors='replace')
    # Chromium needs sparse temporary files larger than the user-code file limit.
    # Render only data, under the same pod's CPU/memory/PID/storage/network limits.
    for spec in sorted(Path('/workspace/plots').glob('figure-*.json'))[:3]:
        remaining=int(os.getenv('QUICK_RUN_SECONDS','30'))-(time.monotonic()-started)
        if remaining<2: break
        renderer=subprocess.Popen([sys.executable,'/opt/lab/render_plot.py',spec.name],stdout=out,stderr=out,start_new_session=True)
        try:
            renderer.wait(timeout=min(14,remaining))
            if renderer.returncode: output+='\nInline image export failed; the interactive HTML is available.\n'
        except subprocess.TimeoutExpired:
            os.killpg(renderer.pid,signal.SIGKILL); renderer.wait()
            output+='\nInline image export timed out; the interactive HTML is available.\n'
print(json.dumps({'stdout':output,'exit_code':process.returncode,'timed_out':timed_out,'artifacts':collect(),'checkpoint':collect_checkpoint()}))
