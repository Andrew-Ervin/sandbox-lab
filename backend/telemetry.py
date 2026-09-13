"""Bounded measured lifecycle history; no prompts, command bodies or secrets."""
import json,re,sqlite3,time


class Telemetry:
    def __init__(self, path):
        self.db=sqlite3.connect(path)
        self.db.executescript('CREATE TABLE IF NOT EXISTS events(at REAL,kind TEXT,resource TEXT,event TEXT,seconds REAL,exit_code INTEGER,error TEXT);CREATE TABLE IF NOT EXISTS samples(at REAL,body TEXT);CREATE INDEX IF NOT EXISTS events_at ON events(at);')
        self.last_sample=0

    def event(self,kind,resource,event,seconds=None,exit_code=None,error=None):
        # Allow diagnostics without storing command output or provider response bodies.
        error=re.sub(r'(Bearer\s+|sk-)[\w.\-]+',r'\1[redacted]',str(error))[:320] if error else None
        with self.db:self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',(time.time(),kind,resource,event,seconds,exit_code,error))

    def sample(self,runtime):
        now=time.time()
        if now-self.last_sample<15:return
        self.last_sample=now;rows={}
        for kind in ('quick','headless','developer'):
            records=[r for r in runtime.records(kind) if r['state']!='deleted']
            running=[r for r in records if r['state']=='running']
            p=runtime.profile(kind)
            rows[kind]={'running':len(running),'warm':sum(bool(r.get('warm')) for r in running),'busy':sum(runtime.active_commands.get(r['id'],0)>0 or r['id'] in getattr(runtime,'resizing',set()) for r in running),'queued':runtime.queued.get(kind,0),'cpu':sum(int(runtime.allocation(r)['cpu'][:-1])/1000 for r in running),'memory_gib':sum(int(runtime.allocation(r)['memory'][:-2])/1024 for r in running),'retained':len(records)}
        if hasattr(runtime,'python_pool_status'):
            pool=runtime.python_pool_status();n=pool['allocated_sessions']
            rows['python']={'running':n,'warm':max(0,n-pool['executing']),'busy':pool['executing'],'queued':pool['queued'],'cpu':n,'memory_gib':n*4,'retained':n}
        body={'roles':rows,'estimated_and_reserved_usd':runtime.budget.status()['estimated_and_reserved_usd']}
        with self.db:
            self.db.execute('INSERT INTO samples VALUES (?,?)',(now,json.dumps(body)))
            self.db.execute('DELETE FROM samples WHERE at<?',(now-7*86400,));self.db.execute('DELETE FROM events WHERE at<?',(now-7*86400,))

    def snapshot(self):
        events=[dict(zip(('at','kind','resource','event','seconds','exit_code','error'),r)) for r in self.db.execute('SELECT * FROM events ORDER BY at DESC LIMIT 200')]
        samples=[{'at':r[0],**json.loads(r[1])} for r in self.db.execute('SELECT at,body FROM samples ORDER BY at DESC LIMIT 1440')][::-1]
        totals=[dict(zip(('kind','event','count','total_seconds','average_seconds','failures'),r)) for r in self.db.execute('SELECT kind,event,COUNT(*),SUM(seconds),AVG(seconds),SUM(error IS NOT NULL OR exit_code!=0) FROM events GROUP BY kind,event')]
        return {'events':events,'samples':samples,'totals':totals,'history_days':7,'allocation_is_not_cpu_utilization':True}
