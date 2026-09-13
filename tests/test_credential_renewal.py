import asyncio,time
from unittest.mock import AsyncMock,Mock
from types import SimpleNamespace
import pytest
from backend.azure_adapters import AzureDeveloper

@pytest.mark.asyncio
@pytest.mark.parametrize('fails',[False,True])
async def test_refresh_precedes_renewal_and_failure_retains_token(monkeypatch,fails):
    adapter=AzureDeveloper.__new__(AzureDeveloper)
    adapter.capability_until={'w':time.time()+10};old=adapter.capability_until['w']
    adapter.touched={'w':time.time()};adapter.runtime=SimpleNamespace(get=AsyncMock(return_value={'id':'w'}));adapter.invoke=AsyncMock()
    refresh=AsyncMock(side_effect=RuntimeError('unavailable') if fails else None)
    issue=Mock(return_value={'expires':time.time()+3600})
    monkeypatch.setattr('backend.workspace_models.refresh',refresh);monkeypatch.setattr('backend.capabilities.issue',issue)
    async def done(_):raise asyncio.CancelledError()
    monkeypatch.setattr('backend.azure_adapters.asyncio.sleep',done)
    with pytest.raises(asyncio.CancelledError):await adapter.maintain_credentials()
    refresh.assert_awaited_once()
    if fails:
        issue.assert_not_called();adapter.invoke.assert_not_awaited();assert adapter.capability_until['w']==old
    else:adapter.invoke.assert_awaited_once();assert adapter.capability_until['w']>old
