"""Operator-only service observations, refreshed off the UI request path."""
import asyncio
import time
from .config import STATE

class ServiceInventory:
    def __init__(self):self.task=None;self.value=None;self.expires=0;self.error=None
    def get(self,control):
        if time.monotonic()>=self.expires and (self.task is None or self.task.done()):self.task=asyncio.create_task(self.refresh(control))
        return {**(self.value or {'observed_at':None,'services':[]}), 'refreshing':bool(self.task and not self.task.done()),'error':self.error}
    async def refresh(self,control):
        try:
            self.value=await control.transport.call('service_inventory',control.profile('quick')['group'],timeout=90);self.error=None
        except Exception as e:self.error=str(e)
        finally:self.expires=time.monotonic()+300

inventory=ServiceInventory()

def local_services(control):
    import os
    storage=control.storage.status()
    storage['weekly_uploaded_bytes']=control.storage.db.execute('SELECT COALESCE(SUM(bytes),0) FROM uploads WHERE created>?',(time.time()-7*86400,)).fetchone()[0]
    storage['max_current_bytes']=1_000_000_000;storage['max_objects']=100
    records=control.records()
    retained={k:sum(r['state']!='deleted' and bool(r.get('sandbox_id')) and not r.get('warm') for r in records if r['kind']==k) for k in ('quick','headless','developer')}
    past=sorted(time.time()-r.get('last_activity_at',r.get('updated_at',time.time())) for r in records if r['state']=='stopped' and r.get('sandbox_id'))
    package={'loaded':False}
    from . import azure_services
    if azure_services._packages is not None:
        from sandbox import package_gateway as p
        files=[f for f in p.CACHE.iterdir() if f.is_file() and len(f.name)==64]
        package={'loaded':True,'cached_bytes':sum(f.stat().st_size for f in files),'capacity_bytes':p.CACHE_BYTES,'artifacts':len(files),'catalog_entries':len(p.downloads),'reserved_bytes':p.reserved_bytes,'active_downloads':sum(p.pins.values()),'minimum_age_days':p.policy().get('minimum_age_days',5)}
    return {'storage':storage,'package_gateway':package,'retained':retained,'oldest_stopped_seconds':max(past,default=0),
            'broker':{'pid':os.getpid(),'sdk_workers':len(control.transport.workers),'active_commands':sum(control.active_commands.values()),'pending_cleanup':sum(bool(r.get('cleanup_pending')) and r['state']!='deleted' for r in records)},
            'model':{'billing':'Per token; separate from Azure compute','recent_calls':control.budget.db.execute("SELECT COUNT(*) FROM charges WHERE kind='model' AND started>?",(time.time()-3600,)).fetchone()[0]},
            'identity':{'authentication':'Microsoft Entra','ownership':'Tenant and user scoped'},
            'session_pool':{'configured':False,'note':'Quick Python uses sandboxes, not a Dynamic Sessions pool. Cloud inventory is authoritative for deployed resources.'}}
