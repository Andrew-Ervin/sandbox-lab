import asyncio,json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.service_inventory import ServiceInventory
from scripts.azure_service_inventory import inventory

@pytest.mark.asyncio
async def test_cloud_inventory_does_not_block_and_preserves_last_observation_on_failure():
    cache=ServiceInventory();block=asyncio.Event()
    async def wait(*args,**kw):await block.wait();return {'observed_at':1,'services':[]}
    control=SimpleNamespace(transport=SimpleNamespace(call=wait),profile=lambda kind:{'group':'test'})
    assert cache.get(control)['refreshing']
    block.set();await cache.task
    assert cache.get(control)['observed_at']==1
    control.transport.call=AsyncMock(side_effect=RuntimeError('Unavailable'));cache.expires=0
    cache.get(control);await cache.task
    assert cache.get(control)['observed_at']==1 and cache.error=='Unavailable'

def test_arm_inventory_returns_only_selected_fields(monkeypatch):
    import scripts.azure_service_inventory as m
    rid='/subscriptions/'+'a'*36+'/resourceGroups/test/providers/Microsoft.Storage/storageAccounts/test'
    def get(request,timeout):
        url=request.full_url
        assert url.startswith('https://management.azure.com/')
        if '/resources?' in url:data={'value':[{'id':rid,'name':'test','type':'Microsoft.Storage/storageAccounts','location':'test','sku':{'name':'Standard_LRS'},'secret':'must not escape'}]}
        elif '/blobServices/' in url:data={'properties':{'isVersioningEnabled':True,'deleteRetentionPolicy':{'days':7}}}
        else:data={'properties':{'provisioningState':'Succeeded','accessTier':'Hot','keys':['must not escape']}}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return json.dumps(data).encode()
        return Response()
    monkeypatch.setattr(m,'urlopen',get)
    result=inventory({'subscription_id':'a'*36,'resource_group':'test'},SimpleNamespace(get_token=lambda scope:SimpleNamespace(token='private')))
    assert 'must not escape' not in json.dumps(result) and 'private' not in json.dumps(result)
    assert result['services'][0]['metrics']['versioning'] is True
