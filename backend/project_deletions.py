"""Durable, bounded project deletion. A browser is never the cleanup worker."""
import asyncio,hashlib,json,re,shutil,time
from pathlib import Path
from fastapi import HTTPException
from chatkit.store import NotFoundError
from .config import STATE


def active_threads(store,tids,owner):
    return any(json.loads(body).get('thread_id') in tids for (body,) in store.db.execute(
        "SELECT body FROM jobs WHERE owner=? AND json_extract(body,'$.status') IN ('queued','running')",(owner,)))


def remove_paths(paths):
    for path in paths:
        if path.is_symlink():path.unlink()
        elif path.is_dir():shutil.rmtree(path)


def purge_records(store,tids):
    # Caller owns the transaction so project deletion is one atomic DB change.
    for tid in tids:
        for table,key in [('thread_preferences','thread'),('project_threads','thread'),('items','thread'),('runs','thread'),('files','thread'),('threads','id')]:
            store.db.execute(f'DELETE FROM {table} WHERE {key}=?',(tid,))
        store.db.execute("DELETE FROM jobs WHERE json_extract(body,'$.thread_id')=?",(tid,))


def cleanup_paths(store,tids,root=STATE):
    paths=[]
    for tid in tids:
        for (rid,) in store.db.execute('SELECT id FROM runs WHERE thread=?',(tid,)):
            if re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',rid):paths.append(root/'artifacts'/rid)
        paths.append(root/'quick-checkpoints'/hashlib.sha256(tid.encode()).hexdigest())
    return paths


class ProjectDeletions:
    def __init__(self,store,step):
        self.store=store;self.step=step;self.tasks={};self.wake=asyncio.Event()
        store.db.executescript('''
        CREATE TABLE IF NOT EXISTS project_deletions(
            id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,
            status TEXT NOT NULL,phase TEXT NOT NULL,error TEXT,
            updated REAL NOT NULL,next_check REAL NOT NULL,retries INTEGER NOT NULL DEFAULT 0,
            submitted INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_project_deletions_due ON project_deletions(status,next_check);
        ''')
        # Previously confirmed deletions from the browser-driven implementation.
        with store.db:
            store.db.execute("INSERT OR IGNORE INTO project_deletions(id,owner,name,status,phase,updated,next_check) SELECT id,owner,name,'deleting','Resuming deletion',?,0 FROM projects WHERE deleting=1",(time.time(),))

    def get(self,pid,owner):
        row=self.store.db.execute('SELECT id,status,phase,error,updated,name,retries,submitted FROM project_deletions WHERE id=? AND owner=?',(pid,owner)).fetchone()
        if not row:raise NotFoundError('Deletion not found')
        return dict(zip(('id','status','phase','error','updated','name','retries','submitted'),row))

    @staticmethod
    def public(value):return {k:v for k,v in value.items() if k not in ('name','retries','submitted')}

    def queue(self,pid,owner,name):
        try:previous=self.get(pid,owner)
        except NotFoundError:previous=None
        if previous and previous['status']=='deleted':
            if name.strip()!=previous['name']:raise HTTPException(400,'Type the project name to confirm deletion')
            return self.public(previous)
        p=self.store.get_project(pid,owner)
        if name.strip()!=p['name']:raise HTTPException(400,'Type the project name to confirm deletion')
        if previous and previous['status']=='deleting':return self.public(previous)
        tids={r[0] for r in self.store.db.execute('SELECT thread FROM project_threads WHERE project=?',(pid,))}
        if active_threads(self.store,tids,owner):raise HTTPException(409,'A conversation is running. Stop its run or wait for it to finish before deleting.')
        with self.store.db:
            self.store.db.execute('UPDATE projects SET deleting=1 WHERE id=?',(pid,))
            self.store.db.execute("INSERT INTO project_deletions(id,owner,name,status,phase,updated,next_check) VALUES (?,?,?,'deleting','Queued for deletion',?,0) ON CONFLICT(id) DO UPDATE SET status='deleting',phase='Queued for deletion',error=NULL,updated=excluded.updated,next_check=0,retries=0,submitted=0",(pid,owner,p['name'],time.time()))
        self.wake.set()
        return self.public(self.get(pid,owner))

    def update(self,pid,phase,*,status='deleting',error=None,delay=2,retries=0):
        now=time.time()
        with self.store.db:self.store.db.execute('UPDATE project_deletions SET status=?,phase=?,error=?,updated=?,next_check=?,retries=? WHERE id=?',(status,phase,error,now,now+delay,retries,pid))

    def submitted(self,pid):
        with self.store.db:self.store.db.execute('UPDATE project_deletions SET submitted=1 WHERE id=?',(pid,))

    async def advance(self,pid,owner):
        operation=self.get(pid,owner)
        if operation['status']!='deleting':return
        try:
            result=await self.step(pid,owner,operation)
            self.update(pid,result['phase'],status=result['status'])
        except HTTPException as exc:
            if exc.status_code==409:
                self.update(pid,str(exc.detail),delay=3);return
            retry=exc.status_code in (429,503,504)
            attempts=operation['retries']+1
            if retry and attempts<8:
                delay=min(60,2**attempts)
                self.update(pid,f'Connection interrupted · retrying in {delay}s',error=str(exc.detail),delay=delay,retries=attempts)
            else:self.update(pid,'Deletion needs attention',status='failed',error=str(exc.detail),retries=attempts)
        except Exception:
            self.update(pid,'Deletion needs attention',status='failed',error='Cleanup could not finish. Files and history not yet removed are retained. Retry deletion.')

    async def maintain(self):
        try:
            while True:
                self.wake.clear()
                available=max(0,2-len(self.tasks))
                if available:
                    rows=self.store.db.execute("SELECT id,owner FROM project_deletions WHERE status='deleting' AND next_check<=? ORDER BY next_check LIMIT ?",(time.time(),available+len(self.tasks))).fetchall()
                    for pid,owner in rows:
                        if pid in self.tasks:continue
                        if len(self.tasks)>=2:break
                        task=asyncio.create_task(self.advance(pid,owner));self.tasks[pid]=task
                        task.add_done_callback(lambda _,pid=pid:(self.tasks.pop(pid,None),self.wake.set()))
                # Small status tombstones make retries idempotent, then expire after a week.
                with self.store.db:self.store.db.execute("DELETE FROM project_deletions WHERE status='deleted' AND updated<?",(time.time()-7*86400,))
                try:await asyncio.wait_for(self.wake.wait(),1)
                except asyncio.TimeoutError:pass
        finally:
            tasks=list(self.tasks.values())
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
