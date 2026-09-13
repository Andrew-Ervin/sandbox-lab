from types import SimpleNamespace
import pytest
from backend import workspace_models as catalog
from backend.azure_services import model_reservation
from backend.config import MODEL

def entry(ident=MODEL,prompt='0.000001',completion='0.000002'):
    return {'id':ident,'pricing':{'prompt':prompt,'completion':completion},'architecture':{'output_modalities':['text']}}

def test_catalog_rejects_unbounded_or_unknown_prices():
    result=catalog.accept([entry(),entry('invalid','NaN'),entry('dynamic','-1')])
    assert list(result)==[MODEL]
    with pytest.raises(ValueError):catalog.accept([entry('other')])

def test_reservation_prices_selected_model(monkeypatch):
    monkeypatch.setattr(catalog,'price',lambda model:{'prompt':.001,'completion':.002,'request':.5})
    body={'model':'other','max_tokens':10}
    reserve=model_reservation(SimpleNamespace(config={}),body)
    assert reserve>8.7

def test_unknown_model_does_not_use_default_price(monkeypatch):
    def missing(model):raise RuntimeError('missing')
    monkeypatch.setattr(catalog,'price',missing)
    with pytest.raises(RuntimeError):model_reservation(SimpleNamespace(config={'model_prices':{'model':MODEL,'prompt':.0001,'completion':.0001}}),{'model':'other'})

def test_catalog_capability_stays_small_and_resolves_only_trusted_catalog(monkeypatch):
    import time
    from backend.capabilities import issue
    from sandbox import gateway
    from starlette.requests import Request
    monkeypatch.setenv('LAB_TOKEN_SECRET','s'*40)
    monkeypatch.setattr(gateway,'secret',b's'*40)
    monkeypatch.setattr(catalog,'_catalog',catalog.accept([entry(),*[entry('vendor/model-'+str(i)) for i in range(500)]]))
    monkeypatch.setattr(catalog,'_updated',time.time())
    monkeypatch.setattr(gateway,'catalog_resolver',catalog.resolve)
    token=issue('workspace')['token']
    assert len(token)<4096
    request=Request({'type':'http','headers':[(b'authorization',('Bearer '+token).encode())]})
    claims=gateway.authorize(request)
    assert len(claims['models'])==501
    monkeypatch.setattr(gateway,'catalog_resolver',lambda _:None)
    with pytest.raises(Exception):gateway.authorize(request)
