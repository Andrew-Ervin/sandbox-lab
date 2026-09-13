import os,json,urllib.request,urllib.error,socket,concurrent.futures
payload=json.dumps({'model':'openai/gpt-5.6-luna','messages':[{'role':'user','content':'Reply OK'}]}).encode()
def check(item):
 name,url,headers=item
 try:
  req=urllib.request.Request(url,data=payload,headers={'Content-Type':'application/json',**headers})
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=4) as r:return name,r.status
 except urllib.error.HTTPError as e:return name,e.code
 except Exception as e:return name,type(e).__name__
checks=[('gateway','http://127.0.0.1:8080/v1/chat/completions',{}),('openrouter','https://openrouter.ai/api/v1/chat/completions',{})]
result={'model_credentials_present':any(os.environ.get(k) for k in ['OPENROUTER_API_KEY','LAB_MODEL_TOKEN','OPENAI_API_KEY'])}
with concurrent.futures.ThreadPoolExecutor() as pool:result.update(dict(pool.map(check,checks)))
try:
 with socket.create_connection(('127.0.0.1',3128),4) as s:
  s.sendall(b'CONNECT openrouter.ai:443 HTTP/1.1\r\nHost: openrouter.ai:443\r\n\r\n');result['proxy_connect']=s.recv(100).decode().split('\r\n')[0]
except Exception as e:result['proxy_connect']=type(e).__name__
print(json.dumps(result))
