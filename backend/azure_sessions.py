"""Observe and stop broker-owned coding runs without any Azure endpoint."""
import asyncio
import json
import time
from .coding_sessions import CodingSessions


class AzureCodingSessions(CodingSessions):
    def __init__(self, headless, store):
        super().__init__(headless,store); self.tasks = {}

    async def read(self, cid, wid, *, force=False):
        record = self.records.get(cid)
        if record and record['workspace_id'] != wid: raise ValueError('Coding session workspace mismatch')
        if not record: record = self.track(cid,wid,'stopped')
        return self.public(record)

    async def for_thread(self, tid, owner):
        thread = await self.store.load_thread(tid,{'owner':owner})
        wid = thread.metadata.get('workspace_id'); cid = thread.metadata.get('azure_coding_session_id')
        sibling = next((r for r in self.records.values() if r['workspace_id']==wid and r['active']),None)
        if sibling: cid = sibling['session_id']
        return await self.read(cid,wid) if cid and wid else None

    async def stop(self, tid, owner, expected_cid):
        current = await self.for_thread(tid,owner)
        if not current or current['session_id'] != expected_cid: raise ValueError('The coding session changed; refresh before stopping.')
        cid,wid = current['session_id'],current['workspace_id']
        self.stops.add(cid); self.stopping.add(wid)
        task = self.tasks.get(cid)
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        try:
            from .previews import previews
            await previews.remove_workspace(wid)
            await self.headless.runtime.stop(wid)
            self.stopping.discard(wid)
            return self.public(self.track(cid,wid,'stopped'))
        except Exception:
            self.track(cid,wid,'stop_failed')
            raise RuntimeError('Azure stop is unconfirmed. The cost lease remains recorded; retry the stop.') from None

    def seed(self):
        for body, in self.store.db.execute('SELECT body FROM threads'):
            metadata = json.loads(body).get('metadata',{})
            cid,wid = metadata.get('azure_coding_session_id'),metadata.get('workspace_id')
            if cid and wid: self.track(cid,wid,'stopped')

    async def maintain(self): await asyncio.Event().wait()
