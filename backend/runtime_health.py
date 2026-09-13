"""Read the local launcher's bounded disk-health snapshot without Docker access."""
import json,time
from .config import STATE

def status():
    from .azure_runtime import runtime
    control=runtime()
    return {'provider':'azure','observed_at':time.time(),'stale':False,'error':control.error,'budget':control.budget.status()}
