"""Durable disposable cleanup, independent of returning a saved Python result."""
import asyncio,time

class QuickCleanup:
    def __init__(self,runtime):self.runtime=runtime;self.tasks={}
    def schedule(self,wid):
        r=self.runtime.record(wid)
        if r['kind']!='quick' or not r.get('disposable') or r.get('warm'):raise ValueError('Only completed disposable Python sandboxes may be queued for deletion')
        if r['state']=='deleted':return
        r['cleanup_pending']=True;self.runtime.save(r)
        if wid not in self.tasks or self.tasks[wid].done():self.tasks[wid]=asyncio.create_task(self.delete(wid))
    async def delete(self,wid):
        started=time.monotonic()
        try:
            await self.runtime.stop(wid,delete=True)
            r=self.runtime.record(wid);r.pop('cleanup_pending',None);r.pop('cleanup_retry_at',None);self.runtime.save(r)
            self.runtime.telemetry.event('quick',wid,'cleanup_completed',seconds=time.monotonic()-started)
        except Exception as e:
            r=self.runtime.record(wid);r['cleanup_retry_at']=time.time()+30;self.runtime.save(r)
            self.runtime.telemetry.event('quick',wid,'cleanup_failed',seconds=time.monotonic()-started,error=str(e))
    def maintain(self):
        self.tasks={k:v for k,v in self.tasks.items() if not v.done()}
        for r in self.runtime.records('quick'):
            if r.get('cleanup_pending') and r['state']!='deleted' and r.get('cleanup_retry_at',0)<=time.time():self.schedule(r['id'])
    async def close(self):await asyncio.gather(*self.tasks.values(),return_exceptions=True)
