import httpx,json,sys
c=httpx.Client(base_url='http://127.0.0.1:3000',timeout=180,trust_env=False)
b=c.post('/api/bootstrap'); b.raise_for_status(); csrf=b.json()['csrf']
payload={'type':'threads.create','params':{'input':{'content':[{'type':'input_text','text':'Use Python to calculate the sum of squares from 0 through 9. Show the result.'}],'attachments':[],'inference_options':{}}}}
r=c.post('/api/chatkit',json=payload,headers={'X-Lab-CSRF':csrf,'X-Lab-Mode':'quick'})
print('HTTP',r.status_code)
for line in r.text.splitlines():
    if line.startswith('data: '):
        data=json.loads(line[6:])
        if data.get('type')=='thread.item.done':
            item=data['item']; print(item['type'],[part.get('text','') for part in item.get('content',[])])
        if data.get('type')=='error': print('ERROR',data)
print('Runs:',[(r['mode'],r['status'],r.get('elapsed')) for r in c.get('/api/status').json().get('runs',[])])
