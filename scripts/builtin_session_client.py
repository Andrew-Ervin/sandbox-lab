"""Server-side built-in Python pool client; never sends Azure tokens into Python."""
import hashlib
import re
from urllib.parse import urlsplit
import httpx


def session_identifier(owner,thread_id):
    if not owner or not thread_id:raise ValueError('Owner and conversation are required')
    return hashlib.sha256((owner+'\0'+thread_id).encode()).hexdigest()


class BuiltinSessions:
    def __init__(self,endpoint,token):
        parsed=urlsplit(endpoint)
        if parsed.scheme!='https' or not re.fullmatch(r'[a-z0-9]+\.dynamicsessions\.io',parsed.hostname or '') or parsed.query or parsed.fragment or parsed.username or parsed.port:
            raise ValueError('Unexpected built-in session endpoint')
        if not re.fullmatch(r'/subscriptions/[a-fA-F0-9-]{36}/resourceGroups/[\w.()-]+/sessionPools/[a-z][a-z0-9]+/?',parsed.path):raise ValueError('Unexpected pool resource path')
        self.endpoint=endpoint.rstrip('/')
        self.http=httpx.AsyncClient(timeout=240,follow_redirects=False,trust_env=False,headers={'Authorization':'Bearer '+token})
    async def execute(self,owner,thread_id,code):
        if not isinstance(code,str) or len(code)>100000:raise ValueError('Invalid Python code')
        response=await self.http.post(self.endpoint+'/code/execute',params={'api-version':'2024-02-02-preview','identifier':session_identifier(owner,thread_id)},
            json={'properties':{'codeInputType':'inline','executionType':'synchronous','code':code}})
        response.raise_for_status()
        return response.json()['properties']
    async def close(self):await self.http.aclose()
