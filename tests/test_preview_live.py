import time
from fastapi.testclient import TestClient
from backend import preview
from starlette.websockets import WebSocketDisconnect
import pytest

@pytest.mark.parametrize('kind,origin,expired', [('artifact','null',False),('app','https://evil.example',False),('app','null',True)])
def test_preview_socket_rejects_untrusted_or_expired_targets(kind,origin,expired):
    preview.targets[9998]={'kind':kind,'expires':time.time()+(-10 if expired else 60),'upstream_port':1}
    try:
        with TestClient(preview.app).websocket_connect('ws://127.0.0.1:9998/',headers={'origin':origin}):
            pytest.fail('unexpected connection')
    except WebSocketDisconnect as exc:assert exc.code==1008
    finally:preview.targets.pop(9998,None)

@pytest.mark.asyncio
async def test_preview_socket_relays_text_and_binary_without_credentials():
    import asyncio, socket, uvicorn
    from websockets.asyncio.server import serve
    from websockets.asyncio.client import connect
    async def echo(ws):
        assert 'cookie' not in ws.request.headers
        assert 'authorization' not in ws.request.headers
        async for message in ws:await ws.send(message)
    async with serve(echo,'127.0.0.1',0,subprotocols=['vite-hmr']) as upstream:
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();sock.setblocking(False)
        port=sock.getsockname()[1]
        preview.targets[port]={'kind':'app','expires':time.time()+60,'upstream_port':upstream.sockets[0].getsockname()[1]}
        server=uvicorn.Server(uvicorn.Config(preview.app,log_level='error'))
        task=asyncio.create_task(server.serve(sockets=[sock]))
        try:
            while not server.started:await asyncio.sleep(.01)
            async with connect(f'ws://127.0.0.1:{port}/hmr?token=test',origin=f'http://127.0.0.1:{port}',subprotocols=['vite-hmr'],additional_headers={'Cookie':'private=yes','Authorization':'Bearer private'},proxy=None) as client:
                assert client.subprotocol=='vite-hmr'
                for message in ['update',b'bytes']:
                    await client.send(message);assert await client.recv()==message
        finally:
            server.should_exit=True;await task;preview.targets.pop(port,None)


def test_editor_activity_renews_only_its_existing_ide_listener(monkeypatch):
    from backend.previews import Previews
    from types import SimpleNamespace
    manager=Previews()
    monkeypatch.setattr(preview,'targets',{
        5001:{'kind':'ide','workspace_id':'one','expires':1},
        5002:{'kind':'ide','workspace_id':'two','expires':1},
        5003:{'kind':'app','workspace_id':'one','expires':1},
    })
    manager.resources={port:{'task':SimpleNamespace(done=lambda:False),'process':None} for port in preview.targets}
    assert manager.renew_workspace('one')
    assert preview.targets[5001]['expires']>time.time()
    assert preview.targets[5002]['expires']==1
    assert preview.targets[5003]['expires']==1
    assert not manager.renew_workspace('missing')
