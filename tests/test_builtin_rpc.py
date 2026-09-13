import json
from urllib.error import HTTPError
from types import SimpleNamespace
import pytest
from scripts import builtin_session_rpc as rpc

ENDPOINT='https://eastus2.dynamicsessions.io/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/test/sessionPools/testpool'

def test_file_transfer_execution_and_result_download(monkeypatch):
 calls=[]
 class Response:
  def __init__(self,req):self.url=req.full_url
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def read(self,n):
   if '/files/content/' in self.url:return b'{"stdout":"ok","artifacts":[]}'
   if '/code/execute' in self.url:return b'{"properties":{"status":"Success","stdout":"LAB_RESULT_READY"}}'
   return b'{}'
 class Opener:
  def open(self,req,timeout):calls.append(req);return Response(req)
 monkeypatch.setattr(rpc,'build_opener',lambda *args:Opener())
 cred=SimpleNamespace(get_token=lambda *args:SimpleNamespace(token='secret-test-token'))
 result=rpc.execute({'builtin_session_endpoint':ENDPOINT},cred,{'identifier':'a'*64,'request':{'code':'print(1)'}})
 assert result['stdout']=='ok'
 assert len(calls)==4 and '/files/upload?' in calls[0].full_url and '/files/content/' in calls[2].full_url
 assert all(b'secret-test-token' not in (c.data or b'') for c in calls)
 assert b'TemporaryDirectory' in calls[1].data

@pytest.mark.parametrize('endpoint',['http://example.org','https://evil.example','https://eastus2.dynamicsessions.io@evil.example/a',ENDPOINT+'?x=y',ENDPOINT.replace('https://','https://:secret@')])
def test_invalid_endpoint_never_gets_credentials(endpoint):
 cred=SimpleNamespace(get_token=lambda *a:pytest.fail('Credential requested'))
 with pytest.raises(ValueError):rpc.execute({'builtin_session_endpoint':endpoint},cred,{'identifier':'a'*64})

def test_execution_is_not_retried_on_ambiguous_failure(monkeypatch):
 calls=[]
 class Opener:
  def open(self,req,timeout):
   calls.append(req)
   if '/code/execute' in req.full_url:raise TimeoutError('unknown')
   return SimpleResponse(req)
 class SimpleResponse:
  def __init__(self,req):self.url=req.full_url
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def read(self,n):return b'{}'
 monkeypatch.setattr(rpc,'build_opener',lambda *args:Opener())
 with pytest.raises(TimeoutError):rpc.execute({'builtin_session_endpoint':ENDPOINT},SimpleNamespace(get_token=lambda *a:SimpleNamespace(token='secret')),{'identifier':'a'*64,'request':{}})
 assert len(calls)==2
