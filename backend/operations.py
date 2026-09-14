"""Measured Azure allocations, execution history, and conservative cost ledger."""
import time
from .azure_runtime import runtime

async def snapshot():
    control=runtime();control.telemetry.sample(control)
    from .service_inventory import inventory,local_services
    charges=[dict(zip(('kind','estimated_spent','reserved','operations'),r)) for r in control.budget.db.execute('SELECT kind,SUM(CASE WHEN ended IS NOT NULL THEN amount ELSE 0 END),SUM(CASE WHEN ended IS NULL THEN amount ELSE 0 END),COUNT(*) FROM charges GROUP BY kind')]
    return {'services':inventory.get(control),'supporting':local_services(control),'observed_at':time.time(),**control.telemetry.snapshot(),'budget':control.budget.status(),'charges':charges,'max_hourly_compute_usd':control.config.get('max_hourly_compute_usd',12),'warm':{k:control.warm.status(k) for k in ('quick','headless','developer')},'storage':control.storage.status(),'errors':[e for e in [control.error,control.billing_error] if e]}
