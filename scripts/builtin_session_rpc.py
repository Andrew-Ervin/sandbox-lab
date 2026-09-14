"""Built-in interpreter execution through the private credential worker.

Payloads/results use the file API, avoiding inline-code and stdout truncation.
No credential is ever placed in code or uploaded files. Never retry execution.
"""
import json,re,uuid
from urllib.request import Request,build_opener,HTTPRedirectHandler,ProxyHandler
from urllib.parse import urlencode,urlsplit

DRIVER = r'''
import json,os,subprocess,sys,tempfile
from pathlib import Path
payload=Path('/mnt/data')/PAYLOAD_NAME
result=Path('/mnt/data')/RESULT_NAME
request=json.loads(payload.read_text())
try:
 with tempfile.TemporaryDirectory(prefix='lab-run-',dir='/mnt/data') as folder:
  root=Path(folder)/'tools';root.mkdir()
  work=Path(folder)/'work';work.mkdir()
  for name,source in request.pop('_sources').items():
   (root/name).write_text(source.replace('/workspace',str(work)).replace('/opt/lab',str(root)))
  request['code']=request['code'].replace('/workspace/',str(work)+'/')
  env={**os.environ,**request.pop('_limits')}
  child=subprocess.run([sys.executable,str(root/'quick.py')],input=json.dumps(request),text=True,capture_output=True,cwd=str(work),env=env,timeout=60)
  if child.returncode:raise RuntimeError(child.stderr[-2000:])
  # Decode before publishing so a corrupt/truncated result fails explicitly.
  value=json.loads(child.stdout)
  with result.open('x') as output:json.dump(value,output)
finally:
 payload.unlink(missing_ok=True)
print('LAB_RESULT_READY')
'''

def execute(config, credential, args):
    endpoint=config['builtin_session_endpoint'].rstrip('/')
    parsed=urlsplit(endpoint)
    if parsed.scheme!='https' or not re.fullmatch(r'[a-z0-9]+\.dynamicsessions\.io',parsed.hostname or '') or parsed.port or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError('Invalid session endpoint')
    if not re.fullmatch(r'/subscriptions/[a-fA-F0-9-]{36}/resourceGroups/[\w.()-]+/sessionPools/[a-z][a-z0-9]+',parsed.path):raise ValueError('Invalid pool path')
    ident=args['identifier']
    if not re.fullmatch('[a-f0-9]{64}',ident):raise ValueError('Invalid session identity')
    token=credential.get_token('https://dynamicsessions.io/.default').token
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=build_opener(ProxyHandler({}),NoRedirect())
    query=urlencode({'api-version':'2024-02-02-preview','identifier':ident})
    def call(path,data=None,content_type=None,maximum=50_000_000):
        headers={'Authorization':'Bearer '+token}
        if content_type:headers['Content-Type']=content_type
        req=Request(endpoint+path+'?'+query,data=data,headers=headers)
        with opener.open(req,timeout=100) as response:
            if response.url!=req.full_url:raise ValueError('Unexpected redirect')
            raw=response.read(maximum+1)
            if len(raw)>maximum:raise ValueError('Session response exceeds limit')
            return raw
    if args.get('delete'):
        req=Request(endpoint+'/session?'+urlencode({'api-version':'2025-02-02-preview','identifier':ident}),headers={'Authorization':'Bearer '+token},method='DELETE')
        from urllib.error import HTTPError
        try:
            with opener.open(req,timeout=30) as response:return {'deleted':True}
        except HTTPError as error:
            if error.code==404:return {'deleted':True}
            raise
    suffix=uuid.uuid4().hex;payload='lab-input-'+suffix+'.json';result='lab-result-'+suffix+'.json'
    raw=json.dumps(args['request']).encode()
    if len(raw)>50_000_000:raise ValueError('Session input exceeds limit')
    boundary='lab-'+uuid.uuid4().hex
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{payload}"\r\nContent-Type: application/json\r\n\r\n'.encode()+raw+f'\r\n--{boundary}--\r\n'.encode())
    call('/files/upload',body,'multipart/form-data; boundary='+boundary)
    code='PAYLOAD_NAME='+repr(payload)+'\nRESULT_NAME='+repr(result)+'\n'+DRIVER
    response=json.loads(call('/code/execute',json.dumps({'properties':{'codeInputType':'inline','executionType':'synchronous','code':code}}).encode(),'application/json',maximum=100000))['properties']
    if response.get('status')!='Success' or 'LAB_RESULT_READY' not in response.get('stdout',''):
        raise RuntimeError('Python session did not finish: '+str(response.get('stderr',''))[:1000])
    raw=call('/files/content/'+result)
    # Clean up only this broker-created result, after confirmed download.
    cleanup='from pathlib import Path\nPath('+repr('/mnt/data/'+result)+').unlink(missing_ok=True)'
    try:call('/code/execute',json.dumps({'properties':{'codeInputType':'inline','executionType':'synchronous','code':cleanup}}).encode(),'application/json',maximum=100000)
    except Exception:pass # Session expiry bounds cleanup on an ambiguous response.
    return json.loads(raw)
