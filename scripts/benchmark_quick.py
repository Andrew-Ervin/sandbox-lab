"""Small local pool benchmark. No model calls; no user conversation changes.

Run: .venv/bin/python -m scripts.benchmark_quick --samples 8
This consumes only its own leased, single-use quick pods. The backend may stay up.
"""
import argparse, asyncio, json, statistics, time, uuid
from backend.compute import Compute

class RunStore:
    def save_run(self,run): pass
    def files(self,thread_id): return []

async def main(samples):
    pool=Compute();pool.policy.warm(); keeper=asyncio.create_task(pool.maintain()); results=[]
    try:
        async with asyncio.timeout(60):
            while len(await pool.pool())<pool.pool_size: await asyncio.sleep(.2)
        async def run_one(index):
            run={'id':'benchmark-'+uuid.uuid4().hex,'thread_id':'benchmark'}
            result=await pool.quick('print(sum(range(100000)))',run,RunStore())
            assert result['stdout'].strip()=='4999950000',result
            results.append({'index':index,**run['timings']})
        for i in range(0,samples,2):
            await asyncio.gather(*(run_one(n) for n in range(i,min(i+2,samples))))
        fields=['queue_seconds','acquire_seconds','execute_seconds','cleanup_seconds','total_seconds']
        print(json.dumps({'samples':results,'summary':{f:{'median':round(statistics.median(r[f] for r in results),4),'max':max(r[f] for r in results)} for f in fields},'note':'Small local smoke sample; not production percentiles or a capacity test. Execution includes kubectl transport, interpreter, code, and result collection.'},indent=2))
    finally:
        keeper.cancel(); await asyncio.gather(keeper,return_exceptions=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--samples',type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.samples<=20: parser.error('samples must be between 1 and 20 on this local lab')
    asyncio.run(main(args.samples))
