"""Project membership and workspace ownership are independent of chat history."""
import json,time,uuid
from chatkit.store import NotFoundError

class ProjectStore:
    def init_projects(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, workspace_id TEXT UNIQUE, created REAL NOT NULL, sync TEXT);
        CREATE TABLE IF NOT EXISTS project_threads(thread TEXT PRIMARY KEY, project TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner);
        CREATE INDEX IF NOT EXISTS idx_project_threads_project ON project_threads(project);
        CREATE TABLE IF NOT EXISTS thread_preferences(thread TEXT PRIMARY KEY, archived INTEGER NOT NULL DEFAULT 0);
        ''')
        columns={r[1] for r in self.db.execute('PRAGMA table_info(projects)')}
        with self.db:
            for column in ('archived','deleting'):
                if column not in columns:self.db.execute(f'ALTER TABLE projects ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0')
            for column in ('developer_workspace_id','developer_name','workspace_sync'):
                if column not in columns:self.db.execute(f'ALTER TABLE projects ADD COLUMN {column} TEXT')
            self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_developer ON projects(developer_workspace_id) WHERE developer_workspace_id IS NOT NULL')

    def get_project(self,project_id,owner):
        row=self.db.execute('SELECT id,name,workspace_id,created,sync,archived,deleting,developer_workspace_id,developer_name,workspace_sync FROM projects WHERE id=? AND owner=?',(project_id,owner)).fetchone()
        if not row:raise NotFoundError('Project not found')
        return dict(zip(('id','name','workspace_id','created','sync','archived','deleting','developer_workspace_id','developer_name','workspace_sync'),(*row[:4],json.loads(row[4]) if row[4] else None,bool(row[5]),bool(row[6]),*row[7:9],json.loads(row[9]) if row[9] else None)))

    def developer_project(self,wid,owner):
        row=self.db.execute('SELECT id FROM projects WHERE developer_workspace_id=? AND owner=?',(wid,owner)).fetchone()
        return self.get_project(row[0],owner) if row else None

    def link_developer(self,wid,owner,name,pid=None):
        existing=self.developer_project(wid,owner)
        if not pid and existing:return existing
        other=self.db.execute('SELECT owner FROM projects WHERE developer_workspace_id=?',(wid,)).fetchone()
        if other and other[0]!=owner:raise NotFoundError('Workspace not found')
        project=self.get_project(pid,owner) if pid else None
        for p in (existing,project):
            if p and (p['archived'] or p['deleting']):raise ValueError('Restore the project or finish deletion before changing its workstation')
        if project and project['developer_workspace_id'] not in (None,wid):raise ValueError('This project already has a developer workstation')
        pid=pid or 'prj_'+uuid.uuid4().hex
        with self.db:
            if not project:self.db.execute('INSERT INTO projects(id,owner,name,created) VALUES(?,?,?,?)',(pid,owner,name[:120],time.time()))
            if existing and existing['id']!=pid:self.db.execute('UPDATE projects SET developer_workspace_id=NULL,developer_name=NULL,workspace_sync=NULL WHERE id=?',(existing['id'],))
            self.db.execute('UPDATE projects SET developer_workspace_id=?,developer_name=? WHERE id=?',(wid,name,pid))
        return self.get_project(pid,owner)

    def project_for_thread(self,thread_id,owner):
        row=self.db.execute('SELECT p.id FROM projects p JOIN project_threads m ON m.project=p.id JOIN threads t ON t.id=m.thread WHERE m.thread=? AND p.owner=? AND t.owner=?',(thread_id,owner,owner)).fetchone()
        return self.get_project(row[0],owner) if row else None

    def projects(self,owner):
        # Two bounded query passes instead of fetching metadata/chats for every project.
        columns=('id','name','workspace_id','created','sync','archived','deleting','developer_workspace_id','developer_name','workspace_sync')
        projects={}
        for row in self.db.execute('SELECT id,name,workspace_id,created,sync,archived,deleting,developer_workspace_id,developer_name,workspace_sync FROM projects WHERE owner=?',(owner,)):
            p=dict(zip(columns,row));p['sync']=json.loads(p['sync']) if p['sync'] else None
            p['workspace_sync']=json.loads(p['workspace_sync']) if p['workspace_sync'] else None
            p['archived']=bool(p['archived']);p['deleting']=bool(p['deleting']);p['threads']=[];projects[p['id']]=p
        for pid,tid,title,updated,archived in self.db.execute("SELECT m.project,t.id,json_extract(t.body,'$.title'),t.updated,COALESCE(a.archived,0) FROM threads t JOIN project_threads m ON m.thread=t.id JOIN projects p ON p.id=m.project LEFT JOIN thread_preferences a ON a.thread=t.id WHERE t.owner=? AND p.owner=? ORDER BY t.updated DESC,t.id",(owner,owner)):
            projects[pid]['threads'].append({'id':tid,'title':title or 'New conversation','updated':updated,'archived':bool(archived)})
        for p in projects.values():p['updated']=p['threads'][0]['updated'] if p['threads'] else p['created']
        return sorted(projects.values(),key=lambda p:(p['updated'],p['id']),reverse=True)

    def thread_summaries(self,owner):
        return [{'id':r[0],'title':r[1] or 'New conversation','updated':r[2],'project_id':r[3],'archived':bool(r[4])} for r in self.db.execute("SELECT t.id,json_extract(t.body,'$.title'),t.updated,m.project,COALESCE(a.archived,0) FROM threads t LEFT JOIN project_threads m ON m.thread=t.id LEFT JOIN thread_preferences a ON a.thread=t.id WHERE t.owner=? ORDER BY t.updated DESC,t.id",(owner,))]

    def update_project(self,pid,owner,*,name=None,archived=None):
        project=self.get_project(pid,owner)
        if project['deleting']:raise ValueError('Project deletion is in progress')
        with self.db:
            if name is not None:
                if not isinstance(name,str) or not 1<=len(name.strip())<=120:raise ValueError('Use a project name between 1 and 120 characters')
                self.db.execute('UPDATE projects SET name=? WHERE id=?',(name.strip(),pid))
            if archived is not None:self.db.execute('UPDATE projects SET archived=? WHERE id=?',(int(archived),pid))

    def archive_thread(self,tid,owner,archived):
        if not self.db.execute('SELECT 1 FROM threads WHERE id=? AND owner=?',(tid,owner)).fetchone():raise NotFoundError('Thread not found')
        with self.db:self.db.execute('INSERT INTO thread_preferences VALUES (?,?) ON CONFLICT(thread) DO UPDATE SET archived=excluded.archived',(tid,int(archived)))

    def check_thread_writable(self,tid,owner):
        project=self.project_for_thread(tid,owner)
        if project and project['deleting']:raise ValueError('Project deletion is in progress')
        if project and project['archived']:raise ValueError('Restore this project before continuing its conversations')
        row=self.db.execute('SELECT archived FROM thread_preferences WHERE thread=?',(tid,)).fetchone()
        if row and row[0]:raise ValueError('Restore this conversation before continuing')

    def attach_project(self,thread,owner,project_id):
        project=self.get_project(project_id,owner)
        row=self.db.execute('SELECT owner FROM threads WHERE id=?',(thread.id,)).fetchone()
        if not row or row[0]!=owner:raise NotFoundError('Thread not found')
        existing=self.project_for_thread(thread.id,owner)
        if existing and existing['id']!=project_id:raise ValueError('This conversation already belongs to another project')
        if thread.metadata.get('coder_workspace_id') and thread.metadata['coder_workspace_id']!=project['workspace_id']:
            raise ValueError('Moving an existing workspace would require an explicit file merge')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO project_threads VALUES (?,?)',(thread.id,project_id))
            self.apply_project_metadata(thread,owner)
            self.db.execute('UPDATE threads SET body=? WHERE id=?',(thread.model_dump_json(),thread.id))
        return project

    def ensure_project(self,thread,owner):
        project=self.project_for_thread(thread.id,owner)
        if not project:
            wid=thread.metadata.get('coder_workspace_id')
            row=self.db.execute('SELECT id,owner FROM projects WHERE workspace_id=?',(wid,)).fetchone() if wid else None
            if row and row[1]!=owner:raise NotFoundError('Workspace not owned by this user')
            pid=row[0] if row else 'prj_'+uuid.uuid4().hex
            with self.db:
                if not row:self.db.execute('INSERT INTO projects (id,owner,name,workspace_id,created) VALUES (?,?,?,?,?)',(pid,owner,thread.title or 'Untitled project',wid,time.time()))
                self.attach_project(thread,owner,pid)
            project=self.get_project(pid,owner)
        if project['archived'] or project['deleting']:raise ValueError('Restore the project or finish its deletion before using its workspace')
        self.apply_project_metadata(thread,owner)
        return project

    def apply_project_metadata(self,thread,owner):
        project=self.project_for_thread(thread.id,owner)
        if not project:return
        wid=thread.metadata.get('coder_workspace_id')
        if project['workspace_id']:
            if wid and wid!=project['workspace_id']:raise ValueError('Project workspace mismatch')
            thread.metadata['coder_workspace_id']=project['workspace_id']
        elif wid:
            self.db.execute('UPDATE projects SET workspace_id=? WHERE id=?',(wid,project['id']))
            # Update siblings without overwriting their messages, titles or agent sessions.
            for tid,body in self.db.execute('SELECT t.id,t.body FROM threads t JOIN project_threads m ON m.thread=t.id WHERE m.project=?',(project['id'],)).fetchall():
                value=json.loads(body);value.setdefault('metadata',{})['coder_workspace_id']=wid
                self.db.execute('UPDATE threads SET body=? WHERE id=?',(json.dumps(value),tid))
        thread.metadata['project_id']=project['id']

    def migrate_projects(self):
        from chatkit.types import ThreadMetadata
        count=0
        for body,owner in self.db.execute('SELECT body,owner FROM threads').fetchall():
            thread=ThreadMetadata.model_validate_json(body)
            if self.project_for_thread(thread.id,owner):continue
            if not thread.metadata.get('coder_workspace_id'):
                rows=self.db.execute("SELECT body FROM runs WHERE thread=? AND json_extract(body,'$.workspace_id') IS NOT NULL ORDER BY created DESC",(thread.id,)).fetchall()
                candidate=next((json.loads(r[0]) for r in rows if json.loads(r[0]).get('mode') in ('analysis','app')),None)
                if not candidate:continue
                thread.metadata['coder_workspace_id']=candidate['workspace_id']
            self.ensure_project(thread,owner);count+=1
        return count

    def save_project_sync(self,project_id,owner,result):
        self.get_project(project_id,owner)
        with self.db:self.db.execute('UPDATE projects SET sync=? WHERE id=? AND owner=?',(json.dumps(result),project_id,owner))
