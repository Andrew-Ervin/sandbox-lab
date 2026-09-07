"""Observe and interrupt native Coder turns independently of chat response jobs."""
import asyncio
import json
import time
from .limits import value
from .native_coder import configuration

TERMINAL = {'waiting', 'error', 'deleted', 'stopped'}

class CodingSessions:
    def __init__(self, coder, store):
        self.coder = coder
        self.store = store
        self.records = {}
        self.locks = {}
        self.stops = set()
        self.stopping = set()
        self.capacity = asyncio.Semaphore(4)
        coder.sessions = self

    @property
    def active_workspaces(self):
        return self.stopping | {r['workspace_id'] for r in self.records.values() if r['active']}

    def track(self, cid, wid, status='unknown'):
        record = self.records.setdefault(cid, {})
        record.update(session_id=cid, workspace_id=wid, status=status,
                      active=status not in TERMINAL, observed_at=time.time(), checked=0)
        return record

    async def read(self, cid, wid, *, force=False):
        async with self.locks.setdefault(cid, asyncio.Lock()):
            record = self.records.get(cid)
            if record and record['workspace_id'] != wid:
                raise ValueError('Coding session workspace mismatch')
            if record and not force and time.monotonic()-record['checked'] < value('NATIVE_STATUS_SECONDS'):
                return self.public(record)
            async with self.capacity:
                try:
                    chat = await self.coder.api('GET', configuration()['api_prefix']+'/'+cid, _timeout=5)
                    if chat.get('workspace_id') != wid:
                        raise ValueError('Coding session workspace mismatch')
                    record = self.track(cid, wid, chat.get('status', 'unknown'))
                    if wid in self.stopping:
                        workspace=await self.coder.api('GET','/api/v2/workspaces/'+wid,_timeout=5)
                        state=workspace['latest_build']['status']
                        if state in ('stopped','deleted'):
                            self.stopping.discard(wid)
                            record=self.track(cid,wid,'stopped')
                        elif state in ('failed','canceled','running'):
                            record=self.track(cid,wid,'stop_failed')
                        else:record=self.track(cid,wid,'stopping_workspace')
                except ValueError:
                    raise
                except Exception as error:
                    record = self.track(cid, wid, 'deleted' if getattr(error, 'status_code', 0) in (404, 410) else 'unknown')
                record['checked'] = time.monotonic()
                return self.public(record)

    def public(self, record):
        return {k: record[k] for k in ('session_id','workspace_id','status','active','observed_at')}

    async def for_thread(self, tid, owner):
        thread = await self.store.load_thread(tid, {'owner': owner})
        cid = thread.metadata.get('native_coder_chat_id')
        wid = thread.metadata.get('coder_workspace_id')
        # Project chats can share a workspace. Surface a still-active sibling
        # turn here too, so the user can stop it without finding its old chat.
        if wid:
            sibling = next((r for r in self.records.values() if r['workspace_id']==wid and r['active']), None)
            if sibling: cid = sibling['session_id']
        return await self.read(cid, wid) if cid and wid else None

    async def stop(self, tid, owner, expected_cid):
        current = await self.for_thread(tid, owner)
        if not current or current['session_id'] != expected_cid:
            raise ValueError('The coding session changed. Refresh its status before stopping.')
        cid, wid = current['session_id'], current['workspace_id']
        # A native interrupt can leave shell children alive. Stop headless
        # compute too; this is the reliable process boundary, retaining its PVC.
        current = await self.read(cid, wid, force=True)
        if current['status'] in ('deleted','stopped'):return current
        self.stops.add(cid)
        self.stopping.add(wid)
        try:
            try:await self.coder.api('POST', configuration()['api_prefix']+'/'+cid+'/interrupt')
            finally:
                from .previews import previews
                await previews.remove_workspace(wid)
                workspace=await self.coder.api('GET','/api/v2/workspaces/'+wid)
                if workspace['latest_build']['status'] not in ('stopping','stopped','deleting','deleted'):
                    await self.coder.api('POST','/api/v2/workspaces/'+wid+'/builds',json={'transition':'stop'})
        except Exception:
            # A failed response can still mean the interrupt was delivered.
            # Keep the marker until the next turn explicitly resets it.
            await self.read(cid, wid, force=True)
            raise RuntimeError('Could not confirm the stop. Check the coding status and retry.') from None
        return self.public(self.track(cid, wid, 'stopping_workspace'))

    def begin(self, cid, wid):
        self.stops.discard(cid)
        self.track(cid, wid, 'running')

    def seed(self):
        for body, in self.store.db.execute('SELECT body FROM threads'):
            metadata=json.loads(body).get('metadata',{})
            cid,wid=metadata.get('native_coder_chat_id'),metadata.get('coder_workspace_id')
            if cid and wid:self.track(cid,wid)

    async def maintain(self):
        while True:
            pending=[(cid,r['workspace_id']) for cid,r in self.records.items() if r['active'] or r['workspace_id'] in self.stopping]
            await asyncio.gather(*(self.read(cid,wid) for cid,wid in pending), return_exceptions=True)
            await asyncio.sleep(value('NATIVE_STATUS_SECONDS'))
