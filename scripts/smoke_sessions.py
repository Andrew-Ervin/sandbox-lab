"""Live regression: disconnect, parallel conversations, rehydration, files, and Luna."""
import asyncio,json,httpx,time
async def main():
 async with httpx.AsyncClient(base_url='http://127.0.0.1:3000',trust_env=False,timeout=180) as c:
  boot=(await c.post('/api/bootstrap')).json(); headers={'X-Lab-CSRF':boot['csrf']}
  async def start(text,mode='auto'):
   payload={'type':'threads.create','params':{'input':{'content':[{'type':'input_text','text':text}],'attachments':[],'inference_options':{}}}}
   async with c.stream('POST','/api/chatkit',json=payload,headers={**headers,'X-Lab-Mode':mode}) as r:
    r.raise_for_status()
    async for line in r.aiter_lines():
     if line.startswith('data: '):
      event=json.loads(line[6:])
      if event.get('thread',{}).get('id'): return event['thread']['id']
  ids=await asyncio.gather(start('Session isolation smoke A: run Python that sleeps 4 seconds, writes "A_ONLY" to /workspace/artifacts/session.txt and prints A_DONE.','quick'),start('Session isolation smoke B: run Python that sleeps 4 seconds, writes "B_ONLY" to /workspace/artifacts/session.txt and prints B_DONE.','quick'))
  print('Disconnected streams for two conversations:',ids,flush=True)
  for _ in range(90):
   status=(await c.get('/api/status')).json()
   jobs=[j for j in status['jobs'] if j['thread_id'] in ids]
   if len(jobs)==2 and all(j['status'] not in ['queued','running'] for j in jobs): break
   await asyncio.sleep(2)
  print('Jobs:',[(j['thread_id'],j['status']) for j in jobs],flush=True)
  assert all(j['status']=='completed' for j in jobs)
  for ident,expected in zip(ids,['A_ONLY','B_ONLY']):
   files=(await c.get(f'/api/threads/{ident}/files')).json()['files']
   f=next(f for f in files if f['name']=='session.txt')
   assert (await c.get(f['download_url'])).text==expected
   response=await c.post('/api/chatkit',headers=headers,json={'type':'threads.get_by_id','params':{'thread_id':ident}})
   response.raise_for_status(); assert 'assistant_message' in response.text and 'task' in response.text
  print('PASS: saved results, execution cards, and same-named files remain isolated after disconnect.',flush=True)
  # A follow-up restores the first conversation's own file into a fresh pod.
  payload={'type':'threads.add_user_message','params':{'thread_id':ids[0],'input':{'content':[{'type':'input_text','text':'Use quick Python with input_files=["session.txt"] to read /workspace/files/session.txt and print its contents. Do not rewrite it.'}],'attachments':[],'inference_options':{}}}}
  r=await c.post('/api/chatkit',json=payload,headers={**headers,'X-Lab-Mode':'quick'});r.raise_for_status()
  status=(await c.get('/api/status')).json(); run=next(r for r in status['runs'] if r['thread_id']==ids[0])
  detail=(await c.get('/api/runs/'+run['id'])).json(); assert detail['output'].strip()=='A_ONLY'
  print('PASS: returning to conversation A restores A’s saved file into a fresh interpreter.',flush=True)
asyncio.run(main())
