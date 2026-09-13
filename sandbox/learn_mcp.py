"""Fixed Microsoft Learn MCP transport for the workspace's approved docs tools.

Stdio for Claude/Codex; `search QUERY` for Pi's terminal tool; no arguments runs
a smoke test. No credential, arbitrary URL, or local package installation.
"""
import json
import sys
import urllib.request

URL='https://learn.microsoft.com/api/mcp'
TOOLS={'microsoft_docs_search','microsoft_docs_fetch','microsoft_code_sample_search'}


class Client:
    def __init__(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        self.headers={'Accept':'application/json, text/event-stream','Content-Type':'application/json'}

    def call(self,method,params=None,ident=1):
        payload={'jsonrpc':'2.0','method':method}
        if params is not None:payload['params']=params
        if ident is not None:payload['id']=ident
        req=urllib.request.Request(URL,data=json.dumps(payload).encode(),headers=self.headers,method='POST')
        with self.opener.open(req,timeout=30) as response:
            session=response.headers.get('Mcp-Session-Id')
            if session:self.headers['Mcp-Session-Id']=session
            if ident is None:return None
            if 'text/event-stream' in response.headers.get('Content-Type',''):
                size=0
                for line in response:
                    size+=len(line)
                    if size>2_000_000:raise ValueError('MCP response exceeds probe limit')
                    if line.startswith(b'data:'):
                        data=json.loads(line[5:])
                        if data.get('id')==ident:break
                else:raise ValueError('MCP stream ended without a response')
            else:
                raw=response.read(2_000_001)
                if len(raw)>2_000_000:raise ValueError('MCP response exceeds limit')
                data=json.loads(raw)
            if 'error' in data:raise RuntimeError('MCP returned a protocol error')
            return data['result']


def handle(client, request):
    if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':raise ValueError('Invalid JSON-RPC request')
    method=request.get('method');params=request.get('params',{})
    if method=='ping':return {}
    if method=='notifications/initialized':return client.call(method,ident=None)
    if method=='notifications/cancelled':return None
    if method not in ('initialize','tools/list','tools/call'):raise ValueError('Unsupported MCP method')
    if method=='tools/call' and params.get('name') not in TOOLS:raise ValueError('Tool is not approved')
    if method=='initialize':
        # No roots, credentials or local-client metadata forwarded upstream.
        params={'protocolVersion':params.get('protocolVersion','2025-03-26'),'capabilities':{},
                'clientInfo':{'name':'sandbox-lab-learn','version':'1.0'}}
    result=client.call(method,params,ident=request.get('id',1))
    if method=='initialize':client.headers['MCP-Protocol-Version']=result['protocolVersion']
    if method=='tools/list':result={**result,'tools':[t for t in result['tools'] if t['name'] in TOOLS]}
    return result


def stdio():
    client=Client()
    while True:
        line=sys.stdin.buffer.readline(1_000_001)
        if not line:return
        if len(line)>1_000_000:raise ValueError('MCP request exceeds limit')
        request={}
        try:
            request=json.loads(line)
            result=handle(client,request)
            response={'jsonrpc':'2.0','id':request.get('id'),'result':result}
        except Exception:
            response={'jsonrpc':'2.0','id':request.get('id') if isinstance(request,dict) else None,
                      'error':{'code':-32000,'message':'Microsoft Learn request failed or is not permitted'}}
        if not isinstance(request,dict) or 'id' in request:
            print(json.dumps(response),flush=True)


def main():
    client=Client()
    initialized=client.call('initialize',{'protocolVersion':'2025-03-26','capabilities':{},
        'clientInfo':{'name':'sandbox-lab-smoke','version':'1.0'}})
    client.headers['MCP-Protocol-Version']=initialized['protocolVersion']
    client.call('notifications/initialized',ident=None)
    tools=client.call('tools/list',{},ident=2)['tools']
    tool=next(t for t in tools if t['name']=='microsoft_docs_search')
    if 'query' not in tool['inputSchema'].get('properties',{}):raise ValueError('Search tool schema changed')
    result=client.call('tools/call',{'name':tool['name'],'arguments':{'query':'Azure Container Apps sandbox suspend resume'}},ident=3)
    if result.get('isError'):raise RuntimeError('MCP search failed')
    print(json.dumps({'server':initialized.get('serverInfo',{}),'tools':[t['name'] for t in tools],
                      'search_ok':bool(result.get('content'))}))


if __name__=='__main__':
    if sys.argv[1:]==['--stdio']:stdio()
    elif len(sys.argv)>2 and sys.argv[1]=='search':
        c=Client();handle(c,{'jsonrpc':'2.0','id':1,'method':'initialize'})
        handle(c,{'jsonrpc':'2.0','method':'notifications/initialized'})
        handle(c,{'jsonrpc':'2.0','id':2,'method':'tools/list'})
        print(json.dumps(handle(c,{'jsonrpc':'2.0','id':3,'method':'tools/call',
            'params':{'name':'microsoft_docs_search','arguments':{'query':' '.join(sys.argv[2:])}}})))
    else:main()
