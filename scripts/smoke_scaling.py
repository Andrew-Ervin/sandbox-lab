"""Live scale-to-zero/cold/warm/burst smoke. Stop the backend's controller first."""
import asyncio,json,time,uuid
from pathlib import Path
from backend.compute import Compute
class Store:
    def save_run(self,run):pass
    def files(self,thread):return []
async def main():
    c=Compute();c.max_concurrency=2;c.slots=asyncio.Semaphore(2);c.max_pods=4;c.pool_size=2;c.policy.maximum=2;c.policy.idle_seconds=2
    keeper=asyncio.create_task(c.maintain());states=[];maximum=0
    async def wait_for(check,seconds=20):
        async with asyncio.timeout(seconds):
            while not check():await asyncio.sleep(.05)
    async def execute(delay=0):
        run={'id':'run_'+uuid.uuid4().hex,'thread_id':'scaling-smoke'}
        result=await c.quick(f'import time;time.sleep({delay});print(42)',run,Store())
        assert result['stdout'].strip()=='42',result
        return run['timings']
    async def monitor():
        nonlocal maximum
        while True:
            maximum=max(maximum,sum(not p.metadata.deletion_timestamp and p.status.phase in ['Pending','Running'] for p in c.cache.values()))
            await asyncio.sleep(.02)
    monitoring=asyncio.create_task(monitor())
    try:
        await wait_for(lambda:c.initialized and not c.cache)
        states.append('zero at rest')
        cold=await execute(1);states.append('cold execution succeeded')
        await wait_for(lambda:c.status()['ready']>=2)
        burst=await asyncio.gather(*(execute(.4) for _ in range(6)));states.append('six queued executions succeeded')
        c.policy.warm_until=0
        await wait_for(lambda:not c.cache);states.append('returned to zero')
        resumed=await execute();states.append('woke from zero again')
        await wait_for(lambda:not c.cache);states.append('returned to zero again')
        assert maximum<=4,maximum
        report={'states':states,'cold':cold,'burst':burst,'resumed':resumed,'max_live_pods':maximum,'pool':c.status(),'note':'Local functional smoke, accelerated two-second idle timer, two execution slots and four total pods. Not production percentiles.'}
        Path('.local/scaling-smoke.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:
        keeper.cancel();monitoring.cancel();await asyncio.gather(keeper,monitoring,return_exceptions=True)
if __name__=='__main__':asyncio.run(main())
