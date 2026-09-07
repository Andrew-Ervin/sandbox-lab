"""Run Ori -> Pi inside one headless Coder workspace; emit only public results/tools."""
import asyncio,json,os,re,signal,sys
from pathlib import Path
from harness_setup import configure

def emit(value): print(json.dumps(value),flush=True)

async def main(request):
    if not re.fullmatch(r'run_[a-f0-9]+',request['run_id']): raise ValueError('Invalid run id')
    if not re.fullmatch(r'thr_[a-f0-9]+',request['thread_id']): raise ValueError('Invalid thread id')
    configure({**request,'gui':False})
    project=Path.home()/'project';project.mkdir(exist_ok=True);(project/'artifacts').mkdir(exist_ok=True)
    sessions=Path.home()/'.pi/agent/sessions';sessions.mkdir(exist_ok=True)
    session=sessions/('lab-'+request['thread_id']+'.jsonl')
    env=dict(os.environ,LAB_MODEL_TOKEN=request['token'],OPENROUTER_API_KEY=request['token'],PI_OFFLINE='1')
    command=[str(Path.home()/'.local/bin/ori-lab'),'--mode','json','--session',str(session),'--append-system-prompt',request['instruction'],'-p',request['prompt']]
    process=await asyncio.create_subprocess_exec(*command,cwd=project,env=env,stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,start_new_session=True,limit=2_000_000)
    directory=Path.home()/'.config/lab/runs';directory.mkdir(exist_ok=True)
    pidfile=directory/(request['run_id']+'.pid');pidfile.write_text(str(process.pid))
    summary='';error='';remaining=40000
    async def drain_errors():
        # Ori startup notices need not enter model output or the chat transcript.
        while await process.stderr.read(4096): pass
    draining=asyncio.create_task(drain_errors())
    try:
        async with asyncio.timeout(int(request.get('timeout_seconds',600))):
            while line:=await process.stdout.readline():
                try: event=json.loads(line)
                except ValueError: continue
                if event.get('type')=='tool_execution_start':
                    args=event.get('args') or {};tool=event.get('toolName','')
                    code=args.get('command') if tool=='bash' else args.get('content') if tool=='write' else args.get('newText') if tool=='edit' else None
                    emit({'type':'lab_progress','tool':tool})
                    if isinstance(code,str) and remaining>0:
                        code=code[:min(remaining,12000)];remaining-=len(code)
                        emit({'type':'lab_tool','tool':tool,'path':str(args.get('path',''))[:240],'code':code})
                if event.get('type')=='message_end' and event.get('message',{}).get('role')=='assistant':
                    message=event['message'];texts=[p.get('text','') for p in message.get('content',[]) if p.get('type')=='text']
                    if texts: summary='\n'.join(texts)[-16000:]
                    if message.get('stopReason')=='error': error=message.get('errorMessage','Agent request failed')[:800]
            await process.wait();await draining
            emit({'type':'lab_result','summary':error or summary or 'Pi completed the turn.','exit_code':1 if error else process.returncode})
    finally:
        if process.returncode is None:
            try: os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: await asyncio.wait_for(process.wait(),5)
            except asyncio.TimeoutError:
                os.killpg(process.pid,signal.SIGKILL);await process.wait()
        draining.cancel();await asyncio.gather(draining,return_exceptions=True)
        pidfile.unlink(missing_ok=True)

if __name__=='__main__': asyncio.run(main(json.load(sys.stdin)))
