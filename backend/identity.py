"""Tenant-bound sign-in and server-side, revocable user sessions."""
import asyncio
import base64
from contextvars import ContextVar
import hashlib
import json
import secrets
import time
import uuid
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from .config import STATE, DOMAIN_KEY

current_owner = ContextVar('current_owner', default=None)


class Identity:
    def __init__(self, root=STATE):
        self.root = root
        path = root/'entra.json'
        self.config = json.loads(path.read_text()) if path.exists() else {}
        self.enabled = bool(self.config)
        self.flows = {}
        self.refresh_locks = {}
        self.keys = None
        self.keys_until = 0
        saved = root/'user-sessions.json'
        self.sessions = json.loads(saved.read_text()) if saved.exists() else {}
        if self.enabled:
            for key in ('tenant_id', 'client_id', 'admin_oid'):
                uuid.UUID(self.config[key])
            if not self.config.get('client_secret'): raise RuntimeError('Sign-in credential is missing')

    @property
    def admin(self):
        return 'entra:'+self.config['tenant_id']+':'+self.config['admin_oid'] if self.enabled else 'local-owner'

    def persist(self):
        for key in list(self.sessions):
            if self.sessions[key]['expires'] <= time.time(): self.sessions.pop(key)
        path = self.root/'user-sessions.json'
        temporary = path.with_suffix('.tmp')
        temporary.touch(mode=0o600, exist_ok=True)
        temporary.write_text(json.dumps(self.sessions)); temporary.chmod(0o600); temporary.replace(path)

    def session(self, token):
        entry = self.sessions.get(token)
        if not entry or entry['expires'] <= time.time(): return None
        if self.enabled and not entry.get('owner', '').startswith('entra:'+self.config['tenant_id']+':'): return None
        if entry.get('provider_expires', entry['expires']) <= time.time(): return None
        return entry

    async def authenticate(self, token):
        entry = self.sessions.get(token)
        if not self.enabled or not entry or not entry.get('refresh_token'):
            return self.session(token)
        if entry['expires'] <= time.time(): return None
        if entry.get('provider_expires', 0) > time.time()+60: return self.session(token)
        lock = self.refresh_locks.setdefault(token, asyncio.Lock())
        async with lock:
            entry = self.sessions.get(token)
            if not entry or entry['expires'] <= time.time(): return None
            if entry.get('provider_expires', 0) > time.time()+60: return self.session(token)
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post('https://login.microsoftonline.com/'+self.config['tenant_id']+'/oauth2/v2.0/token', data={
                        'client_id':self.config['client_id'], 'client_secret':self.config['client_secret'],
                        'grant_type':'refresh_token', 'refresh_token':entry['refresh_token'],
                        'scope':'openid profile email offline_access'})
                if response.status_code >= 500 or response.status_code == 429:
                    raise HTTPException(503, 'Sign-in service is temporarily unavailable. Try again shortly.')
                response.raise_for_status()
                payload = response.json()
                claims = await self.validate_token(payload['id_token'], entry['nonce'], refresh=True)
                if 'entra:'+claims['tid']+':'+claims['oid'] != entry['owner']:
                    raise ValueError('Refreshed identity changed')
            except (httpx.TimeoutException, httpx.NetworkError):
                raise HTTPException(503, 'Sign-in service is temporarily unavailable. Try again shortly.') from None
            except HTTPException:
                raise
            except Exception:
                self.sessions.pop(token, None); self.persist()
                return None
            # Logout or expiry during the network call must not resurrect access.
            if self.sessions.get(token) is not entry or entry['expires'] <= time.time(): return None
            entry['provider_expires'] = float(claims['exp'])
            entry['refresh_token'] = payload.get('refresh_token', entry['refresh_token'])
            self.persist()
            return self.session(token)

    def bootstrap(self, request):
        token = request.cookies.get('lab_session', '')
        entry = self.session(token)
        if not entry:
            if self.enabled:
                return JSONResponse({'signin_required':True, 'login_url':'/api/auth/login'}, status_code=401)
            token = secrets.token_urlsafe(32)
            entry = {'csrf':secrets.token_urlsafe(32), 'owner':'local-owner', 'name':'My account', 'expires':time.time()+28800}
            self.sessions[token] = entry
            self.persist()
        response = JSONResponse({'csrf':entry['csrf'], 'domain_key':DOMAIN_KEY,
            'user':{'id':entry['owner'], 'name':entry['name'], 'admin':entry['owner']==self.admin}, 'auth':'entra' if self.enabled else 'local'})
        response.set_cookie('lab_session',token,httponly=True,samesite='strict',max_age=max(0,int(entry['expires']-time.time())))
        return response

    def login(self, fresh=False):
        if not self.enabled: raise HTTPException(503,'Sign-in has not been configured')
        self.flows = {k:v for k,v in self.flows.items() if v['expires']>time.time()}
        if len(self.flows)>=128: raise HTTPException(429,'Try signing in again shortly')
        state, nonce, verifier, browser = [secrets.token_urlsafe(32) for _ in range(4)]
        self.flows[state] = {'nonce':nonce,'verifier':verifier,'browser':browser,'expires':time.time()+600}
        params = {'client_id':self.config['client_id'],'response_type':'code','response_mode':'query',
            'redirect_uri':self.config['redirect_uri'],'scope':'openid profile email offline_access','state':state,'nonce':nonce,
            'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),'code_challenge_method':'S256'}
        if fresh: params['prompt'] = 'login'
        response = RedirectResponse('https://login.microsoftonline.com/'+self.config['tenant_id']+'/oauth2/v2.0/authorize?'+urlencode(params))
        response.set_cookie('lab_signin',browser,httponly=True,samesite='lax',max_age=600,path='/api/auth')
        return response

    async def validate_token(self, raw, nonce, refresh=False):
        tenant = self.config['tenant_id']
        header = jwt.get_unverified_header(raw)
        if header.get('alg')!='RS256': raise ValueError('Unexpected signing algorithm')
        if self.keys_until < time.time() or not any(k.get('kid')==header.get('kid') for k in (self.keys or [])):
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f'https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys')
                response.raise_for_status(); self.keys=response.json()['keys']; self.keys_until=time.time()+3600
        key = next((k for k in self.keys if k.get('kid')==header.get('kid')), None)
        if not key: raise ValueError('Signing key unavailable')
        claims = jwt.decode(raw,jwt.PyJWK.from_dict(key).key,algorithms=['RS256'],audience=self.config['client_id'],
            issuer=f'https://login.microsoftonline.com/{tenant}/v2.0',options={'require':['exp','iat','nbf','aud','iss','tid','oid'] + ([] if refresh else ['nonce'])},leeway=30)
        if claims['tid']!=tenant or ('nonce' in claims and not secrets.compare_digest(claims['nonce'],nonce)): raise ValueError('Identity does not match sign-in')
        uuid.UUID(claims['oid'])
        return claims

    async def callback(self, request):
        flow = self.flows.pop(request.query_params.get('state',''),None)
        if not flow or flow['expires']<time.time() or not secrets.compare_digest(flow['browser'],request.cookies.get('lab_signin','')):
            raise HTTPException(400,'Sign-in expired or belongs to another browser. Start again.')
        if request.query_params.get('error') or not request.query_params.get('code'):
            return RedirectResponse('/?signin=cancelled')
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post('https://login.microsoftonline.com/'+self.config['tenant_id']+'/oauth2/v2.0/token',data={
                    'client_id':self.config['client_id'],'client_secret':self.config['client_secret'],'grant_type':'authorization_code',
                    'code':request.query_params['code'],'redirect_uri':self.config['redirect_uri'],'code_verifier':flow['verifier']})
                response.raise_for_status()
                payload = response.json()
                claims = await self.validate_token(payload['id_token'],flow['nonce'])
        except Exception:
            raise HTTPException(401,'Sign-in could not be verified. Please try again.') from None
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {'owner':'entra:'+claims['tid']+':'+claims['oid'], 'name':str(claims.get('name','My account'))[:120],
            'csrf':secrets.token_urlsafe(32),'expires':min(time.time()+28800,float(claims['exp']))}
        if payload.get('refresh_token'):
            self.sessions[token].update(refresh_token=payload['refresh_token'], nonce=flow['nonce'],
                provider_expires=float(claims['exp']), expires=time.time()+28800)
        self.persist()
        response = RedirectResponse('/')
        response.set_cookie('lab_session',token,httponly=True,samesite='strict',max_age=int(self.sessions[token]['expires']-time.time()))
        response.delete_cookie('lab_signin',path='/api/auth')
        return response

    def require_admin(self, owner):
        if owner!=self.admin: raise HTTPException(403,'Administrator access required')

    def migrate_legacy(self, store, control):
        """Bind legacy data only to the preselected operator, never first login."""
        if not self.enabled:return
        import sqlite3
        marker=self.root/'entra-owner-migration.done'
        if marker.exists():return
        backup=self.root/'identity-backups'/str(int(time.time()))
        backup.mkdir(parents=True,mode=0o700)
        for name,db in [('history',store.db),('workspaces',control.db)]:
            target=sqlite3.connect(backup/(name+'.sqlite'))
            db.backup(target);target.close();(backup/(name+'.sqlite')).chmod(0o600)
        with store.db:
            for table in ('threads','projects','jobs'):
                store.db.execute(f'UPDATE {table} SET owner=? WHERE owner=?',(self.admin,'local-owner'))
            for ident,body in store.db.execute('SELECT id,body FROM jobs WHERE owner=?',(self.admin,)).fetchall():
                value=json.loads(body);value['owner']=self.admin
                store.db.execute('UPDATE jobs SET body=? WHERE id=?',(json.dumps(value),ident))
        for record in control.records():
            if not record.get('warm') and record.get('owner') in (None,'local-owner'):
                record['owner']=self.admin;control.save(record)
        marker.write_text(self.admin);marker.chmod(0o600)

    def preview_allowed(self, target, cookies):
        if not self.enabled:return True
        entry=self.session(cookies.get('lab_session',''))
        return bool(entry and target.get('owner')==entry['owner'])


identity = Identity()
