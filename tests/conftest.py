import os,tempfile
# Isolate every imported provider from live credentials/state. Explicit runtime
# fixtures use their own fake transport and config.
os.environ['LAB_STATE_DIR']=tempfile.mkdtemp(prefix='sandbox-tests-')
os.environ['SANDBOX_PROVIDER']='azure'

import pytest
@pytest.fixture(autouse=True)
def model_budget_prices(monkeypatch):
    from backend.azure_runtime import runtime
    from backend.config import MODEL
    monkeypatch.setitem(runtime().config,'model_prices',{'model':MODEL,'prompt':0.000001,'completion':0.000002})
