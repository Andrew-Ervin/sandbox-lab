"""Small protocol smoke test to run inside an explicitly allowlisted sandbox.

Discovers tools before using Microsoft Learn search; no LLM, credential, package
installation, or mutation. Production clients should use their MCP SDK.
"""
import json
import urllib.request

URL='https://learn.microsoft.com/api/mcp'


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
            else:data=json.loads(response.read(2_000_001))
            if 'error' in data:raise RuntimeError('MCP returned a protocol error')
            return data['result']


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


if __name__=='__main__':main()
