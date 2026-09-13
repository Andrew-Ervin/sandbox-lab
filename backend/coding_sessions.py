"""Shared coding activity bookkeeping."""
import asyncio,time
TERMINAL={"waiting","error","deleted","stopped"}
class CodingSessions:
    def __init__(self, headless, store):
        self.headless = headless
        self.store = store
        self.records = {}
        self.locks = {}
        self.stops = set()
        self.stopping = set()
        self.capacity = asyncio.Semaphore(4)
        headless.sessions = self

    @property
    def active_workspaces(self):
        return self.stopping | {r['workspace_id'] for r in self.records.values() if r['active']}

    def track(self, cid, wid, status='unknown'):
        record = self.records.setdefault(cid, {})
        record.update(session_id=cid, workspace_id=wid, status=status,
                      active=status not in TERMINAL, observed_at=time.time(), checked=0)
        return record

    def public(self, record):
        return {k: record[k] for k in ('session_id','workspace_id','status','active','observed_at')}

    def begin(self, cid, wid):
        self.stops.discard(cid)
        self.track(cid, wid, 'running')
