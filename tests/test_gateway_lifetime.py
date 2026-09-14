import pytest
@pytest.fixture
def gateway(monkeypatch):
    import importlib.util
    from pathlib import Path
    monkeypatch.setenv('LAB_TOKEN_SECRET','test-secret-'*4)
    monkeypatch.setenv('OPENROUTER_API_KEY','test-only')
    monkeypatch.setenv('OPENROUTER_MODEL','test-model')
    spec=importlib.util.spec_from_file_location('lifetime_gateway',Path(__file__).parents[1]/'sandbox/gateway.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_leaving_one_workspace_keeps_other_workspaces_model_client_open(gateway):
    first=gateway.lifespan(gateway.app);second=gateway.lifespan(gateway.app)
    await first.__aenter__();client=gateway.app.state.upstream
    await second.__aenter__()
    assert gateway.app.state.upstream is client
    await first.__aexit__(None,None,None)
    assert not client.is_closed
    await second.__aexit__(None,None,None)
    assert client.is_closed

def test_preview_server_leaves_main_process_signal_handlers_alone():
    import signal
    import uvicorn
    from backend.previews import PreviewServer
    before=signal.getsignal(signal.SIGTERM)
    with PreviewServer(uvicorn.Config('backend.preview:app')).capture_signals():
        assert signal.getsignal(signal.SIGTERM) is before
    assert signal.getsignal(signal.SIGTERM) is before
