"""Private, conditional Blob checkpoints, independent of sandbox lifetime."""
import asyncio
import base64
import hashlib
import json
import time
import sqlite3
import uuid
from .azure_transport import AzureError


class AzureStorage:
    def __init__(self, runtime):
        self.runtime = runtime
        self.locks = {}
        self.path = runtime.root/'storage-index.json'
        self.index = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.db = sqlite3.connect(runtime.root/'storage-usage.sqlite', isolation_level=None)
        self.db.execute('CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY, bytes INTEGER, created REAL)')
        (runtime.root/'storage-usage.sqlite').chmod(0o600)

    @property
    def enabled(self): return bool(self.runtime.config.get('storage_account'))

    def key(self, kind, identity):
        if kind not in ('workspaces','chats'): raise ValueError('Invalid checkpoint type')
        return kind+'/'+hashlib.sha256(identity.encode()).hexdigest()+'/latest.json'

    async def load(self, kind, identity):
        if not self.enabled: return None
        key = self.key(kind, identity)
        try: result = await self.runtime.transport.call('blob_get','lab-quick',args={'key':key})
        except AzureError as error:
            if error.status_code == 404: return None
            raise
        raw = base64.b64decode(result['data'], validate=True)
        self.index[key] = {'etag':result['etag'], 'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw), 'checked_at':time.time()}
        self.flush()
        return json.loads(raw)

    def flush(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.index)); temporary.chmod(0o600); temporary.replace(self.path)

    async def save(self, kind, identity, payload):
        if not self.enabled: return
        key = self.key(kind, identity)
        raw = json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
        if len(raw) > 70_000_000: raise ValueError('Cloud checkpoint exceeds limit')
        digest = hashlib.sha256(raw).hexdigest()
        async with self.locks.setdefault(key, asyncio.Lock()):
            if key not in self.index: await self.load(kind, identity)
            previous = self.index.get(key,{})
            if previous.get('sha256') == digest: return
            current = sum(x.get('bytes',0) for k,x in self.index.items() if k != key)
            if current+len(raw) > 1_000_000_000 or (key not in self.index and len(self.index)>=100):
                raise RuntimeError('Cloud checkpoint capacity limit reached; local files are preserved')
            # Count attempted writes too: uncertain outcomes must not permit an
            # unbounded version history. Current plus seven-day versions stays
            # bounded by a 2-GB weekly transfer allowance in this pilot.
            self.db.execute('BEGIN IMMEDIATE')
            try:
                used = self.db.execute('SELECT COALESCE(SUM(bytes),0) FROM uploads WHERE created>?',(time.time()-7*86400,)).fetchone()[0]
                if used+len(raw) > 2_000_000_000: raise RuntimeError('Blob checkpoint transfer allowance reached; local files are preserved')
                self.db.execute('INSERT INTO uploads VALUES (?,?,?)',(uuid.uuid4().hex,len(raw),time.time()))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK'); raise
            try:
                result = await self.runtime.transport.call('blob_put','lab-quick',args={
                    'key':key, 'data':base64.b64encode(raw).decode(), 'etag':previous.get('etag')})
            except BaseException:
                # Observe the latest remote ETag before a later, explicit save.
                # Never replay an ambiguous write automatically.
                self.index.pop(key,None);self.flush();raise
            self.index[key] = {'etag':result['etag'],'sha256':digest,'bytes':len(raw),'saved_at':time.time()}
            self.flush()

    async def delete(self,kind,identity):
        if not self.enabled:raise RuntimeError('Cloud storage is unavailable for deletion')
        key=self.key(kind,identity)
        async with self.locks.setdefault(key,asyncio.Lock()):
            try:await self.runtime.transport.call('blob_delete','lab-quick',args={'key':key})
            except AzureError as error:
                if error.status_code!=404:raise
            self.index.pop(key,None);self.flush()

    def status(self):
        return {'enabled':self.enabled, 'provider':'Azure Blob', 'tier':'Standard Hot LRS',
                'checkpoints':len(self.index), 'current_bytes':sum(x.get('bytes',0) for x in self.index.values()),
                'archive_after_days':self.runtime.config.get('archive_after_days'), 'home_archive_max_bytes':600_000_000,
                'archived_workspaces':sum(bool(r.get('cold_archive')) and not r.get('sandbox_id') for r in self.runtime.records()),
                'version_retention_days':7, 'weekly_upload_limit_bytes':2_000_000_000, 'credentials_in_sandboxes':False}
