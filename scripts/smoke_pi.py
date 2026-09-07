"""Exercise ChatKit -> Coder -> Ori -> Pi, then reuse the same session and file."""
import json,sys
from pathlib import Path
import httpx

def main():
    with httpx.Client(base_url='http://127.0.0.1:3000',timeout=720,trust_env=False) as client:
        boot=client.post('/api/bootstrap');boot.raise_for_status()
        headers={'X-Lab-CSRF':boot.json()['csrf'],'X-Lab-Mode':'analysis'}
        def ask(text,thread=None):
            # Routing is automatic; a small Python task alone correctly picks quick.
            text='Perform this integration test in the persistent project workspace using Pi/Ori. Use file and shell tools there to complete the task. '+text
            params={'input':{'content':[{'type':'input_text','text':text}],'attachments':[],'inference_options':{}}}
            if thread: params['thread_id']=thread
            response=client.post('/api/chatkit',headers=headers,json={'type':'threads.add_user_message' if thread else 'threads.create','params':params})
            response.raise_for_status()
            for line in response.text.splitlines():
                if not line.startswith('data: '): continue
                event=json.loads(line[6:])
                if event['type']=='thread.created':thread=event['thread']['id']
            assert thread,'No thread returned'
            runs=[r for r in client.get('/api/status').json()['runs'] if r['thread_id']==thread]
            assert runs and runs[0]['status']=='completed',runs
            run=client.get('/api/runs/'+runs[0]['id']).json()
            assert run.get('engine')=='ori-pi' and run.get('executions'),f"Expected Pi/Ori tools; latest run engine={run.get('engine','quick')}, status={run.get('status')}"
            return thread,run
        thread,first=ask('Pi/Ori integration smoke: run Python to create artifacts/pi-ori-smoke.txt containing exactly FIRST_OK. Confirm by reading the file. Keep the task minimal. Remember the test marker ORI_SESSION_42 for the next turn.',sys.argv[1] if len(sys.argv)>1 else None)
        print(json.dumps({'stage':'first turn passed','thread':thread,'workspace':first['workspace_id'],'timings':first['timings']}),flush=True)
        thread,second=ask('Continue the smoke test. Read artifacts/pi-ori-smoke.txt and assert its content is FIRST_OK. Replace it with SECOND_OK. State the test marker I gave you on the previous turn. Do not do other work.',thread)
        assert first['workspace_id']==second['workspace_id']
        artifact=next(a for a in second['artifacts'] if a['name']=='pi-ori-smoke.txt')
        response=client.get(artifact['download_url']);response.raise_for_status()
        assert response.text.strip()=='SECOND_OK',response.text
        assert 'ORI_SESSION_42' in second['output'],second['output']
        report={'thread':thread,'workspace':second['workspace_id'],'engine':second['engine'],'first':first['timings'],'second':second['timings'],'file_persisted':True,'session_recalled':True,'tool_trace_count':len(second['executions'])}
        Path('.local/pi-handoff-smoke.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
