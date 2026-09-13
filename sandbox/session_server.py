"""HTTP adapter for the existing bounded Python interpreter in Dynamic Sessions.

The platform authenticates ingress. This process holds no cloud/model credentials.
Every operation runs as UID 1000; the root supervisor cannot execute arbitrary
commands supplied by callers. One session runs one request at a time.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import threading
from azure_execute import execute

BUSY = threading.Lock()
MAX_REQUEST = 50_000_000


def interpret(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('code'), str):
        raise ValueError('A code string is required')
    if len(payload['code']) > 100_000: raise ValueError('Code exceeds the limit')
    # Durable files arrive in the explicitly bounded checkpoint, never through
    # ambient reuse of an old container or shared network filesystem.
    root = Path('/workspace')
    for child in root.iterdir():
        if child.is_dir() and not child.is_symlink(): shutil.rmtree(child)
        else: child.unlink()
    request = {k: payload.get(k, default) for k, default in [('code',''),('files',[]),('checkpoint',[])]}
    response = execute({'argv':['python','/opt/lab/quick.py'], 'stdin':json.dumps(request),
                        'cwd':'/workspace', 'timeout':45, 'maximum':66_000_000, 'limits':{}})
    if response['exit_code']: raise RuntimeError('Interpreter supervisor failed')
    return json.loads(response['stdout'])


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass  # Never log code, input data or request URLs.
    def reply(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw))); self.send_header('Connection','close')
        self.end_headers(); self.wfile.write(raw); self.close_connection = True
    def do_GET(self):
        self.reply(200 if self.path.split('?')[0] in ('/health','/ready') else 404, {'ready':True})
    def do_POST(self):
        if self.path.split('?')[0] != '/execute': self.reply(404,{'error':'Unknown operation'}); return
        if self.headers.get('Transfer-Encoding'): self.reply(400,{'error':'Content-Length required'}); return
        try: length = int(self.headers.get('Content-Length','0'))
        except ValueError: length = 0
        if not 0 < length <= MAX_REQUEST: self.reply(413,{'error':'Request exceeds limit'}); return
        if not BUSY.acquire(blocking=False): self.reply(409,{'error':'Session is busy'}); return
        try:
            self.connection.settimeout(60)
            raw = self.rfile.read(length)
            if len(raw) != length: raise ValueError('Incomplete request')
            self.reply(200,interpret(json.loads(raw)))
        except ValueError: self.reply(400,{'error':'Invalid interpreter request'})
        except Exception: self.reply(500,{'error':'Interpreter execution failed'})
        finally: BUSY.release()


if __name__ == '__main__':
    if os.getuid() != 0: raise RuntimeError('The dispatcher must be root to drop child privileges')
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
