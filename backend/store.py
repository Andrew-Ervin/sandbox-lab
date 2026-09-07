import sqlite3, json, uuid
from datetime import datetime
from pydantic import TypeAdapter
from chatkit.store import Store, NotFoundError
from chatkit.types import ThreadMetadata, ThreadItem, Page
from .config import STATE
from .project_store import ProjectStore
ITEM = TypeAdapter(ThreadItem)
class SQLiteStore(ProjectStore, Store[dict]):
    def __init__(self, path=None):
        self.db=sqlite3.connect(path or STATE/'lab.db',check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS threads(id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, thread TEXT NOT NULL, body TEXT NOT NULL, seq INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, thread TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, started REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS files(thread TEXT NOT NULL, name TEXT NOT NULL, run TEXT NOT NULL, size INTEGER NOT NULL, PRIMARY KEY(thread,name));
        CREATE INDEX IF NOT EXISTS idx_items_thread_seq ON items(thread,seq);
        CREATE INDEX IF NOT EXISTS idx_threads_owner_updated ON threads(owner,updated);
        CREATE INDEX IF NOT EXISTS idx_runs_thread_created ON runs(thread,created);
        CREATE INDEX IF NOT EXISTS idx_jobs_owner_started ON jobs(owner,started);''')
        self.init_projects()
        self.db.execute('PRAGMA optimize')
    def generate_thread_id(self, context): return 'thr_'+uuid.uuid4().hex
    def generate_item_id(self, item_type, thread, context): return 'msg_'+uuid.uuid4().hex
    async def load_thread(self, thread_id, context):
        row=self.db.execute('SELECT body FROM threads WHERE id=? AND owner=?',(thread_id,context['owner'])).fetchone()
        if not row: raise NotFoundError('Thread not found')
        return ThreadMetadata.model_validate_json(row[0])
    async def save_thread(self, thread, context):
        row=self.db.execute('SELECT owner,body FROM threads WHERE id=?',(thread.id,)).fetchone()
        if row and row[0]!=context['owner']: raise NotFoundError('Thread not found')
        if row:
            current=json.loads(row[1])
            if current.get('metadata',{}).get('title_version',0)>thread.metadata.get('title_version',0):
                thread.title=current['title']
                for key in ('title_version','title_source','title_pending'):thread.metadata[key]=current['metadata'].get(key)
        with self.db:
            self.apply_project_metadata(thread,context['owner'])
            self.db.execute('INSERT INTO threads VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,updated=excluded.updated',(thread.id,context['owner'],thread.model_dump_json(),datetime.now().timestamp()))
    def _page(self, values, after, limit):
        if after:
            ids=[v.id for v in values]
            if after not in ids: raise NotFoundError('Cursor not found')
            values=values[ids.index(after)+1:]
        data=values[:limit]
        return Page(data=data,has_more=len(values)>limit,after=data[-1].id if len(values)>limit and data else None)
    async def load_threads(self, limit, after, order, context):
        rows=self.db.execute('SELECT t.body FROM threads t LEFT JOIN thread_preferences a ON a.thread=t.id LEFT JOIN project_threads m ON m.thread=t.id LEFT JOIN projects p ON p.id=m.project WHERE t.owner=? AND COALESCE(a.archived,0)=0 AND COALESCE(p.archived,0)=0 AND COALESCE(p.deleting,0)=0 ORDER BY t.updated '+('ASC' if order=='asc' else 'DESC'),(context['owner'],)).fetchall()
        return self._page([ThreadMetadata.model_validate_json(r[0]) for r in rows],after,limit)
    async def load_thread_items(self, thread_id, after, limit, order, context):
        await self.load_thread(thread_id,context)
        if limit<1:raise ValueError('Invalid page size')
        # ChatKit clients may request a larger page. Bound the SQL work and
        # return a valid cursor instead of turning that request into HTTP 500.
        limit=min(limit,1000)
        params=[thread_id];cursor=''
        if after:
            row=self.db.execute('SELECT seq FROM items WHERE id=? AND thread=?',(after,thread_id)).fetchone()
            if not row:raise NotFoundError('Cursor not found')
            cursor=' AND seq '+('>' if order=='asc' else '<')+' ?';params.append(row[0])
        rows=self.db.execute('SELECT body FROM items WHERE thread=?'+cursor+' ORDER BY seq '+('ASC' if order=='asc' else 'DESC')+' LIMIT ?',(*params,limit+1)).fetchall()
        data=[ITEM.validate_json(r[0]) for r in rows[:limit]]
        return Page(data=data,has_more=len(rows)>limit,after=data[-1].id if len(rows)>limit and data else None)
    async def add_thread_item(self, thread_id, item, context): await self.save_item(thread_id,item,context)
    async def save_item(self, thread_id, item, context):
        await self.load_thread(thread_id,context)
        if item.thread_id != thread_id: raise NotFoundError('Wrong thread')
        existing=self.db.execute('SELECT thread FROM items WHERE id=?',(item.id,)).fetchone()
        if existing and existing[0]!=thread_id: raise NotFoundError('Item not found')
        seq=self.db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM items WHERE thread=?',(thread_id,)).fetchone()[0]
        with self.db:
            self.db.execute('INSERT INTO items VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(item.id,thread_id,item.model_dump_json(),seq))
            if not existing and item.type in ['user_message','assistant_message']:
                self.db.execute('UPDATE threads SET updated=? WHERE id=?',(datetime.now().timestamp(),thread_id))
    def set_generated_title(self, thread_id, owner, title, version=1):
        # Read the latest metadata: a background title must never overwrite a workspace claim.
        row=self.db.execute('SELECT body FROM threads WHERE id=? AND owner=?',(thread_id,owner)).fetchone()
        if not row: raise NotFoundError('Thread not found')
        value=json.loads(row[0]);metadata=value.setdefault('metadata',{})
        if metadata.get('title_version',0)>=version:return False
        metadata.update(title_version=version,title_source='ai',title_pending=False);value['title']=title
        with self.db:self.db.execute('UPDATE threads SET body=? WHERE id=? AND owner=?',(json.dumps(value),thread_id,owner))
        return True
    async def load_item(self, thread_id, item_id, context):
        await self.load_thread(thread_id,context)
        row=self.db.execute('SELECT body FROM items WHERE id=? AND thread=?',(item_id,thread_id)).fetchone()
        if not row: raise NotFoundError('Item not found')
        return ITEM.validate_json(row[0])
    async def delete_thread(self, thread_id, context):
        await self.load_thread(thread_id,context)
        with self.db:
            self.db.execute('DELETE FROM thread_preferences WHERE thread=?',(thread_id,))
            self.db.execute('DELETE FROM project_threads WHERE thread=?',(thread_id,))
            self.db.execute('DELETE FROM items WHERE thread=?',(thread_id,))
            self.db.execute('DELETE FROM threads WHERE id=?',(thread_id,))
    async def delete_thread_item(self, thread_id, item_id, context):
        await self.load_thread(thread_id,context)
        with self.db: self.db.execute('DELETE FROM items WHERE id=? AND thread=?',(item_id,thread_id))
    async def save_attachment(self, attachment, context): raise NotImplementedError('Uploads disabled')
    async def load_attachment(self, attachment_id, context): raise NotFoundError('Uploads disabled')
    async def delete_attachment(self, attachment_id, context): raise NotFoundError('Uploads disabled')
    def save_run(self, run):
        with self.db: self.db.execute('INSERT INTO runs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(run['id'],run['thread_id'],json.dumps(run),datetime.now().timestamp()))
    def runs(self, owner, limit=60, *, details=True):
        body="r.body" if details else "json_remove(r.body, '$.code', '$.task', '$.output', '$.executions')"
        return [json.loads(r[0]) for r in self.db.execute(f'SELECT {body} FROM runs r JOIN threads t ON r.thread=t.id WHERE t.owner=? ORDER BY r.created DESC LIMIT ?',(owner,limit)).fetchall()]
    def get_run(self, run_id, owner):
        row=self.db.execute('SELECT r.body FROM runs r JOIN threads t ON r.thread=t.id WHERE r.id=? AND t.owner=?',(run_id,owner)).fetchone()
        return json.loads(row[0]) if row else None
    def apps(self, owner):
        # Gallery lifetime is independent of the recent execution history window.
        rows=self.db.execute("SELECT json_remove(r.body, '$.code', '$.task', '$.output', '$.executions'),t.body FROM runs r JOIN threads t ON r.thread=t.id WHERE t.owner=? AND json_extract(r.body,'$.preview_url') IS NOT NULL ORDER BY r.created DESC",(owner,)).fetchall()
        result=[]; seen=set()
        for body,thread in rows:
            run=json.loads(body)
            key=run.get('workspace_id') or run.get('pod') or run['id']
            if run.get('gallery_hidden') or key in seen: continue
            seen.add(key)
            result.append({**{k:v for k,v in run.items() if k not in ['code','task','output','executions']},'title':json.loads(thread).get('title')})
        return result
    def save_job(self, job):
        with self.db: self.db.execute('INSERT INTO jobs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(job['id'],job['owner'],json.dumps(job),job['started']))
    def jobs(self, owner):
        return [json.loads(r[0]) for r in self.db.execute("SELECT body FROM jobs WHERE owner=? ORDER BY CASE WHEN json_extract(body,'$.status') IN ('queued','running') THEN 0 ELSE 1 END,started DESC LIMIT 100",(owner,)).fetchall()]
    def recover_jobs(self):
        for row in self.db.execute('SELECT body FROM jobs').fetchall():
            job=json.loads(row[0])
            if job['status'] in ['queued','running']:
                job.update(status='interrupted',progress='Server restarted. Send a follow-up to continue; files were retained.')
                self.save_job(job)
        for row in self.db.execute('SELECT body FROM runs').fetchall():
            run=json.loads(row[0])
            if run['status'] in ['starting','queued','running','provisioning']:
                run['status']='interrupted'; self.save_run(run)
    def remember_file(self, thread_id, name, run_id, size):
        with self.db: self.db.execute('INSERT INTO files VALUES(?,?,?,?) ON CONFLICT(thread,name) DO UPDATE SET run=excluded.run,size=excluded.size',(thread_id,name,run_id,size))
    def files(self, thread_id):
        return [{'name':r[0],'run_id':r[1],'size':r[2], 'url':f'/api/artifact-view/{r[1]}/{r[0]}','download_url':f'/api/artifacts/{r[1]}/{r[0]}'} for r in self.db.execute('SELECT name,run,size FROM files WHERE thread=? ORDER BY name',(thread_id,)).fetchall()]
