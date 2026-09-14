import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.health import HealthCache
from backend.live import AzureLiveContainers

@pytest.mark.asyncio
async def test_health_returns_while_cloud_is_stalled():
    gate=asyncio.Event()
    async def slow():await gate.wait();return []
    cache=HealthCache();compute=SimpleNamespace(pool=slow,ready=False)
    result=await asyncio.wait_for(cache.get(compute,SimpleNamespace(ready=slow)),.1)
    assert result['health_refreshing']
    cache.task.cancel();await asyncio.gather(cache.task,return_exceptions=True)

@pytest.mark.asyncio
async def test_inventory_returns_local_metadata_without_waiting(monkeypatch):
    gate=asyncio.Event()
    async def slow(kind):await gate.wait();return []
    control=SimpleNamespace(list=slow,records=lambda:[{'id':'w','name':'saved','kind':'headless','state':'stopped'}],profile=lambda kind:{'group':kind})
    monkeypatch.setattr('backend.azure_runtime.runtime',lambda:control)
    cache=AzureLiveContainers();result=await asyncio.wait_for(cache.get(),.1)
    assert result['stale'] and result['pods'][0]['name']=='saved'
    cache.task.cancel();await asyncio.gather(cache.task,return_exceptions=True)
