import json
import time
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from backend.identity import Identity


@pytest.fixture
def auth(tmp_path):
    config = {k: str(uuid.uuid4()) for k in ('tenant_id', 'client_id', 'admin_oid')}
    config.update(client_secret='test-only', redirect_uri='http://127.0.0.1:3000/api/auth/callback')
    (tmp_path/'entra.json').write_text(json.dumps(config))
    return Identity(tmp_path)


@pytest.mark.asyncio
async def test_signed_token_requires_tenant_audience_nonce_and_expiry(auth):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));jwk['kid']='test'
    auth.keys=[jwk];auth.keys_until=time.time()+60
    claims={'tid':auth.config['tenant_id'],'oid':auth.config['admin_oid'],'nonce':'expected',
            'aud':auth.config['client_id'],'iss':f"https://login.microsoftonline.com/{auth.config['tenant_id']}/v2.0",
            'iat':int(time.time()),'nbf':int(time.time())-1,'exp':int(time.time())+60}
    encode=lambda value:jwt.encode(value,key,algorithm='RS256',headers={'kid':'test'})
    assert (await auth.validate_token(encode(claims),'expected'))['oid']==auth.config['admin_oid']
    for field,value in [('aud','foreign'),('tid',str(uuid.uuid4())),('nonce','wrong'),('exp',int(time.time())-100)]:
        with pytest.raises((ValueError,jwt.InvalidTokenError)):
            await auth.validate_token(encode({**claims,field:value}),'expected')


@pytest.mark.asyncio
async def test_signin_flow_is_browser_bound_and_single_use(auth):
    response=auth.login();params=parse_qs(urlsplit(response.headers['location']).query)
    assert params['code_challenge_method']==['S256']
    state=params['state'][0]
    with pytest.raises(HTTPException) as error:
        await auth.callback(SimpleNamespace(query_params={'state':state,'code':'ignored'},cookies={'lab_signin':'different-browser'}))
    assert error.value.status_code==400 and state not in auth.flows
    assert auth.bootstrap(SimpleNamespace(cookies={})).status_code==401
    auth.sessions['legacy']={'owner':'local-owner','expires':time.time()+60}
    assert auth.session('legacy') is None


@pytest.mark.asyncio
async def test_other_user_cannot_open_modify_or_see_workspace(auth,monkeypatch,tmp_path):
    import backend.main as main
    from backend.store import SQLiteStore
    store=SQLiteStore(tmp_path/'history.db');store.link_developer('alice-workspace',auth.admin,'Private')
    owner='entra:'+auth.config['tenant_id']+':'+str(uuid.uuid4())
    auth.sessions['bob']={'owner':owner,'csrf':'csrf','name':'Bob','expires':time.time()+60}
    monkeypatch.setattr(main,'identity',auth);monkeypatch.setattr(main,'store',store);monkeypatch.setattr(main,'sessions',auth.sessions)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://127.0.0.1:8787',cookies={'lab_session':'bob'},headers={'x-lab-csrf':'csrf'}) as client:
        for method,suffix in [('GET','/open'),('GET','/preview'),('POST','/heartbeat'),('PATCH','/name'),('PATCH','/compute'),('POST','/preferences'),('DELETE','')]:
            response=await client.request(method,'/api/developer/workspaces/alice-workspace'+suffix,json={})
            assert response.status_code==404
        assert (await client.get('/api/operations')).status_code==403
        assert (await client.get('/api/threads')).json()==[]
        assert (await client.post('/api/auth/logout')).status_code==200
        assert auth.session('bob') is None


def test_preview_requires_same_owner_and_revocable_session(auth):
    auth.sessions['a']={'owner':auth.admin,'expires':time.time()+60}
    target={'owner':auth.admin}
    assert auth.preview_allowed(target,{'lab_session':'a'})
    assert not auth.preview_allowed(target,{})
    assert not auth.preview_allowed({'owner':'other'},{'lab_session':'a'})
    auth.sessions.pop('a');assert not auth.preview_allowed(target,{'lab_session':'a'})


@pytest.mark.asyncio
async def test_legacy_migration_preserves_rows_and_backs_up_to_fixed_admin(auth,tmp_path):
    import sqlite3
    from datetime import datetime,timezone
    from chatkit.types import ThreadMetadata
    from backend.store import SQLiteStore
    store=SQLiteStore(tmp_path/'legacy.db')
    await store.save_thread(ThreadMetadata(id='legacy',created_at=datetime.now(timezone.utc)),{'owner':'local-owner'})
    project=store.link_developer('workspace','local-owner','My files')
    rows=[{'id':'workspace','owner':None},{'id':'spare','warm':True}]
    control=SimpleNamespace(db=sqlite3.connect(':memory:'),records=lambda:rows,save=lambda record:None)
    auth.migrate_legacy(store,control)
    assert (await store.load_thread('legacy',{'owner':auth.admin})).id=='legacy'
    assert store.get_project(project['id'],auth.admin)['developer_workspace_id']=='workspace'
    assert rows[0]['owner']==auth.admin and 'owner' not in rows[1]
    backups=list((tmp_path/'identity-backups').glob('*/history.sqlite'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute('SELECT owner FROM threads').fetchone()[0]=='local-owner'
    auth.migrate_legacy(store,control)
    assert len(list((tmp_path/'identity-backups').iterdir()))==1

@pytest.mark.asyncio
async def test_refresh_rotates_once_preserves_absolute_expiry_and_owner(auth, monkeypatch):
    import asyncio
    expiry=time.time()+2000
    auth.sessions['token']={'owner':auth.admin,'expires':expiry,'provider_expires':time.time()-1,
        'refresh_token':'old','nonce':'nonce','csrf':'csrf'}
    calls=[]
    async def post(client,url,**kwargs):
        calls.append(kwargs['data']);await asyncio.sleep(.01)
        return httpx.Response(200,json={'id_token':'signed','refresh_token':'new'},request=httpx.Request('POST',url))
    async def validate(raw,nonce,refresh=False):
        assert refresh and nonce=='nonce'
        return {'tid':auth.config['tenant_id'],'oid':auth.config['admin_oid'],'exp':time.time()+1000}
    monkeypatch.setattr(httpx.AsyncClient,'post',post);monkeypatch.setattr(auth,'validate_token',validate)
    entries=await asyncio.gather(*(auth.authenticate('token') for _ in range(5)))
    assert len(calls)==1 and all(e['owner']==auth.admin for e in entries)
    assert entries[0]['refresh_token']=='new' and entries[0]['expires']==expiry
    assert auth.session('token') is not None

@pytest.mark.asyncio
@pytest.mark.parametrize('status,revoked',[(400,True),(503,False),(429,False)])
async def test_refresh_denial_revokes_but_transient_failure_keeps_recovery(auth,monkeypatch,status,revoked):
    auth.sessions['token']={'owner':auth.admin,'expires':time.time()+500,'provider_expires':time.time()-1,
        'refresh_token':'old','nonce':'nonce'}
    async def post(client,url,**kwargs):
        return httpx.Response(status,json={'error':'invalid_grant'},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    if revoked: assert await auth.authenticate('token') is None
    else:
        with pytest.raises(HTTPException) as exc: await auth.authenticate('token')
        assert exc.value.status_code==503
    assert ('token' not in auth.sessions)==revoked
    assert auth.session('token') is None

def test_fresh_signin_requests_interactive_flow_and_refresh_scope(auth):
    params=parse_qs(urlsplit(auth.login(fresh=True).headers['location']).query)
    assert params['prompt']==['login']
    assert 'offline_access' in params['scope'][0].split()

@pytest.mark.asyncio
async def test_refresh_rejects_account_change_and_never_extends_absolute_expiry(auth,monkeypatch):
    calls=[]
    async def post(client,url,**kwargs):
        calls.append(1)
        return httpx.Response(200,json={'id_token':'signed'},request=httpx.Request('POST',url))
    async def validate(*args,**kwargs):
        return {'tid':auth.config['tenant_id'],'oid':str(uuid.uuid4()),'exp':time.time()+1000}
    monkeypatch.setattr(httpx.AsyncClient,'post',post);monkeypatch.setattr(auth,'validate_token',validate)
    auth.sessions['expired']={'owner':auth.admin,'expires':time.time()-1,'refresh_token':'old'}
    assert await auth.authenticate('expired') is None and not calls
    auth.sessions['changed']={'owner':auth.admin,'expires':time.time()+500,'provider_expires':0,'nonce':'nonce','refresh_token':'old'}
    assert await auth.authenticate('changed') is None
    assert 'changed' not in auth.sessions
