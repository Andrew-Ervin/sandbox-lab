"""One clean, unassigned Coder workspace; never recycle a conversation home."""
import asyncio,json,os,time,uuid
from .config import STATE

class ProjectReserve:
    def __init__(self,coder,path=None):
        self.coder=coder;self.path=path or STATE/'project-reserve.json';self.error=None;self.state='asleep';self.hits=0
        self.enabled=os.getenv('PROJECT_WARM_RESERVE','1')=='1'
        self.idle=float(os.getenv('PROJECT_RESERVE_IDLE_SECONDS','300'))
        try:self.record=json.loads(self.path.read_text())
        except (OSError,ValueError):self.record={}
    def save(self):
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.record));temp.chmod(0o600);temp.replace(self.path)
    def request(self):
        if self.enabled:self.record['until']=time.time()+self.idle;self.save()
    def wanted(self):return self.enabled and self.record.get('until',0)>time.time()
    def protected(self,wid):return self.wanted() and self.record.get('workspace_id')==wid
    def attached(self,store,wid):
        if store.db.execute('SELECT 1 FROM projects WHERE workspace_id=?',(wid,)).fetchone():return True
        return bool(store.db.execute("SELECT 1 FROM threads WHERE json_extract(body,'$.metadata.coder_workspace_id')=? LIMIT 1",(wid,)).fetchone())
    def status(self):return {'enabled':self.enabled,'state':self.state,'workspace_id':self.record.get('workspace_id'),'target':int(self.wanted()),'idle_seconds':self.idle,'claims':self.hits,'error':self.error}
    async def claim(self,thread,store,context):
        # Caller owns coder.provision_lock. Save ownership before clearing the ledger,
        # so a crash cannot turn an attached project back into spare capacity.
        wid=self.record.get('workspace_id')
        if not wid:return None
        if self.attached(store,wid):
            self.record.pop('workspace_id',None);self.save();return None
        try:ws=await self.coder.api('GET','/api/v2/workspaces/'+wid)
        except RuntimeError as error:
            if getattr(error,'status_code',0) not in (404,410):raise
            self.record.pop('workspace_id',None);self.save();self.state='asleep';return None
        if ws.get('deleted') or ws['template_id']!=self.coder.settings()['template_id']:
            self.record.pop('workspace_id',None);self.save();return None
        status=ws['latest_build']['status']
        if status in ['stopping','deleting']:return None
        if status in ['stopped','failed','canceled'] or ws.get('outdated'):
            await self.coder.ensure_capacity(wid)
            template=await self.coder.api('GET','/api/v2/templates/'+ws['template_id'])
            await self.coder.api('POST','/api/v2/workspaces/'+wid+'/builds',json={'transition':'start','template_version_id':template['active_version_id']})
        thread.metadata['coder_workspace_id']=wid;await store.save_thread(thread,context)
        self.record.pop('workspace_id',None);self.save();self.state='claimed';self.hits+=1
        self.coder.touched[wid]=time.time();return wid
    async def reconcile(self,store):
        async with self.coder.provision_lock:
            wid=self.record.get('workspace_id')
            if wid and self.attached(store,wid):
                self.record.pop('workspace_id',None);self.save();wid=None
            settings=self.coder.settings()
            if not wid:
                if not self.wanted():self.state='asleep';return
                result=await self.coder.api('GET','/api/v2/workspaces',params={'q':'owner:me'})
                if sum(not w.get('deleted') and w['template_id']==settings['template_id'] for w in result.get('workspaces',[]))>=int(os.getenv('AI_MAX_RETAINED_WORKSPACES','50')):self.state='retained-home capacity full';return
                running=sum(w['latest_build']['status'] in ['running','pending','starting','stopping'] for w in result.get('workspaces',[]) if not w.get('deleted') and w['template_id']==settings['template_id'])
                # Speculation never evicts an actual project to make space.
                if running>=self.coder.max_running:self.state='capacity full';return
                ws=await self.coder.api('POST',f"/api/v2/organizations/{settings['organization_id']}/members/me/workspaces",json={'name':'reserve-'+uuid.uuid4().hex[:12],'template_id':settings['template_id'],'ttl_ms':int(self.idle*1000)})
                wid=ws['id'];self.record['workspace_id']=wid;self.save();self.coder.touched[wid]=time.time()
            try:ws=await self.coder.api('GET','/api/v2/workspaces/'+wid)
            except RuntimeError as error:
                if getattr(error,'status_code',0) not in (404,410):raise
                self.record.pop('workspace_id',None);self.save();self.state='asleep';return
            if ws['template_id']!=settings['template_id']:
                self.record.pop('workspace_id',None);self.save();self.state='asleep';return
            state=ws['latest_build']['status']
            if ws.get('deleted'):
                self.record.pop('workspace_id',None);self.save();self.state='asleep';return
            if not self.wanted():
                if state=='running':await self.coder.api('POST','/api/v2/workspaces/'+wid+'/builds',json={'transition':'stop'});state='stopping'
                self.state=state;return
            if state in ['stopped','failed','canceled']:
                result=await self.coder.api('GET','/api/v2/workspaces',params={'q':'owner:me'})
                if sum(w['latest_build']['status'] in ['running','pending','starting','stopping'] for w in result.get('workspaces',[]) if not w.get('deleted'))>=self.coder.max_running:self.state='capacity full';return
                template=await self.coder.api('GET','/api/v2/templates/'+settings['template_id'])
                await self.coder.api('POST','/api/v2/workspaces/'+wid+'/builds',json={'transition':'start','template_version_id':template['active_version_id']});state='starting'
            agents=[a for r in ws['latest_build'].get('resources',[]) for a in r.get('agents',[])]
            self.state='ready' if state=='running' and any(a['status']=='connected' for a in agents) else 'starting' if state=='running' else state
    async def maintain(self,store):
        while True:
            try:await self.reconcile(store);self.error=None
            except Exception:self.state='unavailable';self.error='Project reserve will retry; on-demand allocation remains available.'
            await asyncio.sleep(5)
