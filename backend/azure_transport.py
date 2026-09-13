"""Private SDK worker transport; Azure credentials never enter sandbox requests."""
import asyncio
import base64
import json
import os
import struct
from .config import ROOT, STATE


class AzureError(RuntimeError):
    def __init__(self, action, status=None):
        self.status_code = status
        super().__init__(f'Azure {action} could not complete'+(f' (HTTP {status})' if status else '')+'. Check Azure access and sandbox status before retrying.')


class AzureTransport:
    def __init__(self, config):
        self.config = config
        self.slots = asyncio.Semaphore(8)
        self.idle = []
        self.workers = set()

    async def close(self):
        workers = list(self.workers); self.workers.clear(); self.idle.clear()
        for process in workers:
            if process.returncode is None: process.kill()
        await asyncio.gather(*(p.wait() for p in workers), return_exceptions=True)

    async def call(self, action, group, sandbox_id=None, args=None, timeout=240):
        root = STATE/'azure-pilot'
        env = {**os.environ, 'AZURE_CONFIG_DIR': str(root/'azure-config'),
               'PATH': str(root/'az-venv/bin')+os.pathsep+os.environ.get('PATH','')}
        worker = root/'sdk-venv/bin/python'
        if not worker.exists(): raise RuntimeError('Install the isolated Azure SDK with scripts/setup_azure_runtime.py first.')
        async with self.slots:
            process = self.idle.pop() if self.idle else None
            if process is None or process.returncode is not None:
                if process: self.workers.discard(process)
                process = await asyncio.create_subprocess_exec(str(worker), str(ROOT/'scripts/azure_sandbox_rpc.py'), '--stream',
                            env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                self.workers.add(process)
            data = {'config': self.config, 'action': action, 'group': group, 'sandbox_id': sandbox_id, 'args': args or {}}
            healthy = False
            try:
                async with asyncio.timeout(timeout):
                    raw = json.dumps(data).encode()
                    if len(raw) > 180_000_000: raise RuntimeError('Azure request exceeded the transfer limit')
                    process.stdin.write(struct.pack('!I',len(raw))+raw); await process.stdin.drain()
                    size = struct.unpack('!I', await process.stdout.readexactly(4))[0]
                    if size > 180_000_000: raise RuntimeError('Azure response exceeded the transfer limit')
                    out = await process.stdout.readexactly(size)
                result = json.loads(out)
                healthy = True
                if 'error' in result: raise AzureError(action, result.get('status_code'))
                return result['result']
            finally:
                if healthy and process.returncode is None: self.idle.append(process)
                else:
                    self.workers.discard(process)
                    if process.returncode is None: process.kill(); await process.wait()

    async def write(self, group, sid, path, content, mode='0600'):
        return await self.call('write', group, sid, {'path': path, 'data': base64.b64encode(content).decode(), 'mode': mode})

    async def read(self, group, sid, path, maximum):
        data = await self.call('read', group, sid, {'path': path, 'maximum': maximum})
        return base64.b64decode(data['data'], validate=True)
