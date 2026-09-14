import asyncio,json,time
from types import SimpleNamespace
import pytest
from sandbox.azure_bridge import Bridge

@pytest.mark.asyncio
async def test_package_head_has_length_without_body_and_other_head_routes_denied():
    b=Bridge({'token':'test','deadline':time.time()+60})
    async def send(raw):
        req=json.loads(raw);q=b.pending[req['id']]
        await q.put({'type':'headers','status':200,'content_type':'application/octet-stream','content_length':123})
        await q.put({'type':'end'})
    b.reverse=SimpleNamespace(send=send)
    class Writer:
        def __init__(self):self.data=b''
        def write(self,data):self.data+=data
        async def drain(self):pass
        def close(self):pass
        async def wait_closed(self):pass
    for path,allowed in [('/artifact/'+'a'*64+'/test.whl',True),('/python/simple/test/',False),('/arbitrary',False)]:
        r=asyncio.StreamReader();r.feed_data(f'HEAD {path} HTTP/1.1\r\nHost: localhost\r\n\r\n'.encode());r.feed_eof();w=Writer()
        await b.http(r,w,'package')
        assert w.data.startswith(b'HTTP/1.1 200' if allowed else b'HTTP/1.1 503')
        if allowed:assert b'Content-Length: 123' in w.data and w.data.endswith(b'\r\n\r\n')
