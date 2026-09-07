"""End-to-end ChatKit/OpenRouter execution. Creates clearly named test conversations."""
import json,time
import httpx

c=httpx.Client(base_url='http://127.0.0.1:3000',timeout=720,trust_env=False)
boot=c.post('/api/bootstrap'); boot.raise_for_status()
headers={'X-Lab-CSRF':boot.json()['csrf']}

def ask(prompt,mode):
    response=c.post('/api/chatkit',headers={**headers,'X-Lab-Mode':mode},json={'type':'threads.create','params':{'input':{'content':[{'type':'input_text','text':prompt}],'attachments':[],'inference_options':{}}}})
    response.raise_for_status(); thread=None
    for line in response.text.splitlines():
        if not line.startswith('data: '): continue
        event=json.loads(line[6:])
        if event['type']=='thread.created': thread=event['thread']['id']
        if event['type']=='thread.item.done':
            item=event['item']; thread=thread or item['thread_id']
            if item['type']=='assistant_message': print('\n'.join(x.get('text','') for x in item['content']),flush=True)
    runs=[r for r in c.get('/api/status').json()['runs'] if r['thread_id']==thread]
    assert runs and all(r['status']=='completed' for r in runs), [(r['status'],r.get('summary')) for r in runs]
    return runs[0]

chart=ask('Smoke test: use plotly.graph_objects to chart y=x*x for integers 0 to 10, and save a self-contained HTML file with include_plotlyjs=True.','quick')
assert chart['artifacts'],chart
with httpx.Client(timeout=30,trust_env=False) as public:
    r=c.get(chart['artifacts'][0]['url'],follow_redirects=True); assert r.status_code==200,r.status_code
    assert 'sandbox' in r.headers.get('content-security-policy','')
    assert len(r.content)>2_000_000,'The chart should include Plotly for offline rendering'
print('Quick chart and isolated artifact serving passed.',flush=True)

project=ask('Smoke test: build a tiny Go web application in the project using the standard library. On GET / return HTML with heading "Lab preview 42". Start the compiled HTTP server in the background on 0.0.0.0:3000 and keep it running. Save artifacts/README.txt with build and run instructions. Do not spawn sub-agents.','app')
assert project.get('preview_url'),project
with httpx.Client(timeout=30,trust_env=False) as public:
    for _ in range(30):
        r=c.get(project['preview_url'],follow_redirects=True)
        if r.status_code==200: break
        time.sleep(1)
    assert r.status_code==200 and 'Lab preview 42' in r.text,(r.status_code,r.text[:200])
    assert 'allow-same-origin' not in r.headers['content-security-policy']
assert project['artifacts'],project
print('Pi / Ori, Go app, artifact collection, and isolated preview passed.',flush=True)
print(json.dumps({'chat_thread':project['thread_id'],'workspace':project['workspace_id'],'preview_url':project['preview_url']}),flush=True)
