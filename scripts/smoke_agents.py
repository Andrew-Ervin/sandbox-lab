import asyncio,json,uuid
from datetime import datetime,timezone
from chatkit.types import ThreadMetadata
from backend.store import SQLiteStore
from backend.coder import coder
async def main():
    store=SQLiteStore(); context={'owner':'local-owner'}
    thread=ThreadMetadata(id='thr_'+uuid.uuid4().hex,title='Coder Agents smoke test',created_at=datetime.now(timezone.utc))
    await store.save_thread(thread,context)
    run={'id':'run_'+uuid.uuid4().hex,'thread_id':thread.id,'mode':'analysis','status':'starting','artifacts':[]}; store.save_run(run)
    result=await coder.run(thread,'Create hello.py in /home/sandbox/project that prints 42. Run it, then save the output in artifacts/result.txt. Do not spawn sub-agents. Report the exact result.', 'analysis',run,store,context)
    store.save_run(run)
    print(json.dumps(result,indent=2)); print('Run status:',run['status'])
asyncio.run(main())
