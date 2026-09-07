"""Verify an Ori/Pi-built Go server survives the agent turn and serves the preview."""
import json
from pathlib import Path
import httpx

with httpx.Client(base_url='http://127.0.0.1:3000',timeout=720,trust_env=False) as c:
    thread=json.loads(Path('.local/pi-handoff-smoke.json').read_text())['thread']
    boot=c.post('/api/bootstrap');boot.raise_for_status()
    prompt='Pi/Ori app smoke: in a new pi-preview subdirectory write a minimal Go standard-library HTTP server. GET / returns HTML with heading "Pi Ori Go preview 42". Build it and start the binary listening on 0.0.0.0:3000 in the background with stdin closed and stdout/stderr redirected to a log. Verify it with curl. Keep it running after this turn. Save artifacts/pi-preview-README.txt with the build/start command. Preserve existing project files; do nothing else.'
    response=c.post('/api/chatkit',headers={'X-Lab-CSRF':boot.json()['csrf'],'X-Lab-Mode':'app'},json={'type':'threads.add_user_message','params':{'thread_id':thread,'input':{'content':[{'type':'input_text','text':prompt}],'attachments':[],'inference_options':{}}}})
    response.raise_for_status()
    run=next(r for r in c.get('/api/status').json()['runs'] if r['thread_id']==thread)
    assert run['status']=='completed' and run['engine']=='ori-pi',run
    preview=c.get(run['preview_url'],follow_redirects=True);preview.raise_for_status()
    assert 'Pi Ori Go preview 42' in preview.text
    assert 'sandbox' in preview.headers['content-security-policy'] and 'allow-same-origin' not in preview.headers['content-security-policy']
    report={'thread':thread,'workspace':run['workspace_id'],'run':run['id'],'preview':run['preview_url'],'timings':run['timings'],'status':'passed'}
    Path('.local/pi-app-smoke.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
