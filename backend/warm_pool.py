"""Clean standby capacity, assigned once; no cross-project home reuse."""
import asyncio
import time
import uuid


class WarmPool:
    def __init__(self, runtime):
        self.runtime=runtime; self.until={}; self.tasks={}; self.hits=0; self.misses=0
        self.paused=False

    def demand(self, kind):
        self.paused=False
        self.until[kind]=time.time()+600

    def status(self, kind):
        records=[r for r in self.runtime.records(kind) if r.get('warm') and r['state']!='deleted']
        return {'ready':sum(r['state']=='running' for r in records),'target':int(self.until.get(kind,0)>time.time() and not self.paused), 'warm_until':self.until.get(kind,0),'hits':self.hits,'misses':self.misses}

    def claim(self, kind, name, *, disposable=False, compute_size=None):
        # Called under the allocator lock. Standby never contains user work.
        for r in self.runtime.records(kind):
            if r.get('warm') and (kind!='developer' or r.get('compute_size','performance')==(compute_size or 'balanced')) and r['state']=='running' and r.get('lease_until',0)>time.time()+60:
                r.update(warm=False,disposable=disposable or kind=='quick',name=name,last_activity_at=time.time())
                self.runtime.save(r);self.hits+=1;return r
        self.misses+=1

    async def maintain(self):
        async def reconcile(kind):
            records=[r for r in self.runtime.records(kind) if r.get('warm') and r['state']!='deleted']
            wanted=self.until.get(kind,0)>time.time() and not self.paused and not self.runtime.budget.status()['blocked']
            if not wanted:
                for r in records:
                    try:await self.runtime.stop(r['id'],delete=True)
                    except Exception:self.runtime.telemetry.event(kind,r['id'],'warm_cleanup_failed',error='Standby cleanup unconfirmed')
            else:
                try:
                    if not records:await self.runtime.create(kind,'standby-'+uuid.uuid4().hex[:12],disposable=True,warm=True)
                    elif records[0]['state']=='creating' and not records[0].get('create_submitted'):
                        await self.runtime.start(records[0]['id'],standby=True)
                except Exception as e:self.runtime.telemetry.event(kind,'','warm_unavailable',error=str(e))
        try:
            while True:
                # A queued warm admission must not block cleanup or readiness
                # for the other roles. Never queue multiple spares for one role.
                for kind in ('quick','headless','developer'):
                    if kind not in self.tasks or self.tasks[kind].done():
                        self.tasks[kind]=asyncio.create_task(reconcile(kind))
                await asyncio.sleep(5)
        finally:
            for task in self.tasks.values():task.cancel()
            await asyncio.gather(*self.tasks.values(),return_exceptions=True)

    def pause(self):
        self.paused=True;self.until.clear();self.runtime.admission_generation+=1
