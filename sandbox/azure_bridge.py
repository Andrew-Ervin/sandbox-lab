"""Authenticated per-sandbox relay. No shell, file, URL, or arbitrary-port API.

Runs as root with a root-only credential. Generated code runs as uid 1000 with
no_new_privs. Azure ingress terminates TLS; only this port is published.
"""
import asyncio
import base64
import http
import json
from pathlib import Path
import secrets
import time
import uuid
from websockets.asyncio.server import serve


class Bridge:
    def __init__(self, config):
        self.token = config['token']
        self.developer = config.get('developer', False)
        self.reverse = None
        self.pending = {}
        self.slots = asyncio.Semaphore(16)
        self.tcp_slots = asyncio.Semaphore(64)
        self.deadline = config['deadline']

    async def authenticate(self, connection, request):
        if time.time() >= self.deadline:
            return connection.respond(http.HTTPStatus.GONE, 'Lease expired\n')
        if not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer '+self.token):
            return connection.respond(http.HTTPStatus.UNAUTHORIZED, 'Authentication required\n')
        if request.path not in ('/tcp/3000', '/services') and not (self.developer and request.path == '/tcp/13337'):
            return connection.respond(http.HTTPStatus.NOT_FOUND, 'Unknown route\n')

    async def socket(self, connection):
        path = connection.request.path
        if path == '/services':
            if self.reverse:
                await connection.close(code=1008); return
            self.reverse = connection
            try:
                await connection.send(json.dumps({'type': 'ready'}))
                async for raw in connection:
                    data = json.loads(raw)
                    queue = self.pending.get(data.get('id'))
                    if queue: await queue.put(data)
            finally:
                self.reverse = None
                for queue in self.pending.values():
                    # Pending HTTP readers time out if their bounded queue is full.
                    if not queue.full(): queue.put_nowait({'type': 'error'})
            return
        async with self.tcp_slots:
            port = int(path.rsplit('/', 1)[-1])
            try: reader, writer = await asyncio.open_connection('127.0.0.1', port)
            except OSError:
                await connection.close(code=1013); return
            async def inward():
                async for data in connection:
                    if not isinstance(data, bytes): raise ValueError('Binary data required')
                    writer.write(data); await writer.drain()
            async def outward():
                while data := await reader.read(65536): await connection.send(data)
            tasks = [asyncio.create_task(inward()), asyncio.create_task(outward())]
            try: await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks: task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                writer.close(); await writer.wait_closed()

    async def http(self, reader, writer, service):
        ident = uuid.uuid4().hex
        try:
            async with self.slots, asyncio.timeout(240):
                header = await reader.readuntil(b'\r\n\r\n')
                if len(header) > 16000: raise ValueError('Headers too large')
                lines = header.decode('latin1').split('\r\n')
                method, path, version = lines[0].split(' ')
                fields = {}
                for line in lines[1:]:
                    if line:
                        key, val = line.split(':', 1)
                        if key.lower() in fields: raise ValueError('Duplicate header')
                        fields[key.lower()] = val.strip()
                if 'transfer-encoding' in fields: raise ValueError('Chunked requests unavailable')
                if not path.startswith('/') or path.startswith('//') or len(path) > 4096: raise ValueError('Invalid path')
                gallery_query=service=='package' and method=='POST' and path=='/vscode/gallery/extensionquery'
                maximum = 2_000_000 if service == 'model' else (16000 if gallery_query else 0)
                length = int(fields.get('content-length', '0'))
                if not 0 <= length <= maximum: raise ValueError('Body too large')
                if service=='model':
                    from urllib.parse import urlsplit,parse_qs
                    parsed=urlsplit(path);query=parse_qs(parsed.query)
                    if parsed.path=='/v1/messages' and all(k=='beta' and v==['true'] for k,v in query.items()):path=parsed.path
                    elif parsed.path=='/v1/models' and all(k=='client_version' and len(v)==1 and len(v[0])<40 for k,v in query.items()):path=parsed.path
                    if (method,path) not in (('POST','/v1/chat/completions'),('POST','/v1/responses'),('POST','/v1/messages'),('GET','/v1/models')):raise ValueError('Route denied')
                elif method!='GET' and not gallery_query:raise ValueError('Method denied')
                if not self.reverse: raise RuntimeError('Broker disconnected')
                body = await reader.readexactly(length)
                queue = asyncio.Queue(maxsize=8); self.pending[ident] = queue
                await self.reverse.send(json.dumps({'id': ident, 'service': service, 'method': method, 'path': path,
                    'authorization': (fields.get('authorization') or ('Bearer '+fields['x-api-key'] if fields.get('x-api-key') else '')) if service == 'model' else '',
                    'body': base64.b64encode(body).decode()}))
                first = await queue.get()
                if first.get('type') != 'headers': raise RuntimeError('Service unavailable')
                status = int(first['status']); content_type = first.get('content_type', 'application/octet-stream')
                if '\r' in content_type or '\n' in content_type: raise ValueError('Invalid response')
                writer.write(f'HTTP/1.1 {status} Response\r\nContent-Type: {content_type}\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n'.encode())
                while True:
                    part = await queue.get()
                    if part.get('type') == 'end': break
                    if part.get('type') != 'body': raise RuntimeError('Service disconnected')
                    chunk = base64.b64decode(part['data'], validate=True)
                    writer.write(f'{len(chunk):x}\r\n'.encode()+chunk+b'\r\n'); await writer.drain()
                writer.write(b'0\r\n\r\n'); await writer.drain()
        except Exception:
            try: writer.write(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'); await writer.drain()
            except OSError: pass
        finally:
            self.pending.pop(ident, None); writer.close()
            try: await writer.wait_closed()
            except OSError: pass

    async def run(self):
        async with serve(self.socket, '0.0.0.0', 18443, process_request=self.authenticate,
                         max_size=3_000_000, max_queue=8, compression=None, ping_interval=20):
            servers = [await asyncio.start_server(lambda r,w: self.http(r,w,'package'), '127.0.0.1', 3128, limit=16000)]
            if self.developer:
                servers.append(await asyncio.start_server(lambda r,w: self.http(r,w,'model'), '127.0.0.1', 8080, limit=16000))
            try: await asyncio.sleep(max(0, self.deadline-time.time()))
            finally:
                for server in servers: server.close(); await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(Bridge(json.loads(Path('/var/lib/lab/bridge.json').read_text())).run())
