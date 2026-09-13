"""Conversation Python in a built-in pool, with durable broker-owned files."""
import asyncio,base64,hashlib,json,time
from .azure_adapters import AzureQuick
from .identity import current_owner
from .config import ROOT
from .limits import value
from . import checkpoints
from .files import inputs

class BuiltinPython(AzureQuick):
    provider='azure-sessions'
    def __init__(self):
        super().__init__()
        self.runtime.python_pool_status=self.status
        self.capacity=int(self.runtime.config.get('builtin_session_limit',10))
        self.slots=asyncio.Semaphore(self.capacity)
        self.runtime.budget.db.execute('CREATE TABLE IF NOT EXISTS python_sessions(identifier TEXT PRIMARY KEY, started REAL, expires REAL, paid_hours INTEGER)')

    async def pool(self):
        if not self.runtime.config.get('builtin_session_endpoint'):raise RuntimeError('Configure the built-in Python pool endpoint')
        self.ready=True
        return []

    def status(self):
        live=self.runtime.budget.db.execute('SELECT COUNT(*) FROM python_sessions WHERE expires>?',(time.time(),)).fetchone()[0]
        return {'provider':self.provider,'queued':self.queued,'executing':self.executing,'ready':int(self.ready),
            'target_reserve':0,'minimum_reserve':0,'max_concurrency':self.capacity,'max_pods':self.capacity,
            'allocated_sessions':live,'idle_seconds':3300,'warm_hits':0,'cold_misses':0,'refill_seconds':0,
            'error':self.error,'budget':self.runtime.budget.status()}

    def account(self,identity):
        # Persist across broker restarts. Include the request deadline for execution/transfer
        # when estimating the final idle expiry; count unknown outcomes as used.
        now=time.time();db=self.runtime.budget.db
        row=db.execute('SELECT started,expires,paid_hours FROM python_sessions WHERE identifier=?',(identity,)).fetchone()
        if not row or row[1]<=now:
            live=db.execute('SELECT COUNT(*) FROM python_sessions WHERE expires>?',(now,)).fetchone()[0]
            if live>=self.capacity:raise RuntimeError('Python sessions are at the pilot allocation limit. Wait for an idle session to expire; the request has not executed.')
            started=now;paid=0
        else:started,_,paid=row
        import math
        expiry=now+3450;hours=math.ceil((expiry-started)/3600)
        if hours>paid:
            charge=self.runtime.budget.reserve('builtin-python',.03*(hours-paid))
            self.runtime.budget.finish(charge) # Estimated allocated session-hours, not a provider bill.
        db.execute('INSERT OR REPLACE INTO python_sessions VALUES (?,?,?,?)',(identity,started,expiry,hours))

    async def quick(self,code,run,store,input_files=None):
        if not isinstance(code,str) or len(code)>100000:raise ValueError('Invalid Python code')
        owner=current_owner.get()
        if not owner:raise RuntimeError('Python execution requires a signed-in owner')
        identity=hashlib.sha256((owner+'\0'+run['thread_id']).encode()).hexdigest()
        self.queued+=1;entered=False;begin=time.monotonic()
        try:
            async with self.thread_locks.setdefault(identity,asyncio.Lock()),self.slots:
                entered=True;self.queued-=1;self.executing+=1
                run['timings']={'queue_seconds':time.monotonic()-begin}
                try:
                    saved=checkpoints.load(run['thread_id'])
                    if not (checkpoints.directory(run['thread_id'])/'latest.json').exists() and self.runtime.storage.enabled:
                        blob=await self.runtime.storage.load('chats',run['thread_id'])
                        if blob:saved=checkpoints.validate(blob['files'])
                    files=inputs(store,run['thread_id'],input_files or [])
                    self.account(identity)
                    run.update(pod='python-session',status='running',compute_provider=self.provider);store.save_run(run)
                    names=['quick.py','checkpoint.py','collect.py','plot_capture.py','render_plot.py']
                    request={'code':code,'files':files,'checkpoint':saved,
                        '_sources':{n:(ROOT/'sandbox'/n).read_text() for n in names},
                        '_limits':{k:str(value(k)) for k in ['QUICK_RUN_SECONDS','QUICK_CPU_SECONDS','QUICK_STDOUT_BYTES','ARTIFACT_MAX_FILES','ARTIFACT_MAX_FILE_BYTES','ARTIFACT_MAX_TOTAL_BYTES']}}
                    phase=time.monotonic()
                    result=await self.runtime.transport.call('builtin_execute',self.runtime.profile('quick')['group'],args={'identifier':identity,'request':request},timeout=150)
                    run['timings']['execution_seconds']=time.monotonic()-phase
                    checkpoint=result.pop('checkpoint',None)
                    if checkpoint is not None:
                        run['checkpoint']=checkpoints.save(run['thread_id'],run['id'],checkpoint);result['checkpoint']=run['checkpoint']
                        await self.runtime.storage.save('chats',run['thread_id'],{'files':checkpoints.validate(checkpoint.get('files',[])),'truncated':bool(checkpoint.get('truncated'))})
                    result.setdefault('artifacts',[]).insert(0,{'name':'quick-source.py','data':base64.b64encode(code.encode()).decode()})
                    self.runtime.telemetry.event('python',identity,'execute',seconds=time.monotonic()-begin,exit_code=result.get('exit_code'))
                    return result
                except Exception as error:
                    self.runtime.telemetry.event('python',identity,'execute_failed',seconds=time.monotonic()-begin,error=type(error).__name__)
                    raise
                finally:
                    self.executing-=1;run['timings']['total_seconds']=time.monotonic()-begin;store.save_run(run)
        finally:
            if not entered:self.queued-=1
