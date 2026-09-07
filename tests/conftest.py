import pytest
@pytest.fixture(autouse=True)
def isolate_project_reserve_ledger(tmp_path,monkeypatch):
    from backend.coder import coder
    monkeypatch.setattr(coder.reserve,'path',tmp_path/'reserve.json')
    monkeypatch.setattr(coder.reserve,'record',{})
