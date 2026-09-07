"""Three-way source synchronization; credentials and dependency trees never cross."""
import asyncio,base64,hashlib,json,re,time
from .config import ROOT

def reconcile(base,chat,developer,blocked=()):
    """Return direction-specific changes and conflicts, including tracked deletions."""
    changes={'chat':{},'developer':{}};conflicts=[];agreed={}
    for path in sorted(set(base)|set(chat)|set(developer)):
        if any(path==p or path.startswith(p+'/') for p in blocked):conflicts.append(path);continue
        a,b,old=chat.get(path),developer.get(path),base.get(path)
        if a==b:
            if a is not None:agreed[path]=a
        elif a==old:changes['chat'][path]=b
        elif b==old:changes['developer'][path]=a
        else:conflicts.append(path)
    return changes,conflicts,agreed

def manifest(payload):
    result={}
    for item in payload['files']:
        path=item['path'];digest=item['sha256']
        from .projects import safe_path
        safe_path(path)
        if path in result or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('Invalid source manifest')
        result[path]=digest
    return result

class SourceSync:
    def __init__(self,links):self.links=links;self.event=asyncio.Event();self.background=set()
    def request(self):self.event.set()

    async def run(self,p,owner,chat,developer,*,resolution=None):
        links=self.links;store=links.store;paths=links.paths(p)
        binding=[p['workspace_id'],p['developer_workspace_id'],*paths]
        row=store.db.execute('SELECT body FROM source_sync_state WHERE project=?',(p['id'],)).fetchone()
        previous=json.loads(row[0]) if row else {}
        base=previous.get('base',{}) if previous.get('binding')==binding else {}
        destinations={'chat':chat,'developer':developer}
        adapters={'chat':None,'developer':links.developer}
        scopes=dict(zip(('chat','developer'),paths))
        payloads=await asyncio.gather(*(links.browser.read(destinations[side],'manifest',path=scopes[side],developer=adapters[side]) for side in ('chat','developer')))
        snapshots={side:manifest(payload) for side,payload in zip(('chat','developer'),payloads)}
        blocked=[path for payload in payloads for path in payload.get('blocked',[])]
        changes,conflicts,agreed=reconcile(base,snapshots['chat'],snapshots['developer'],blocked)
        if resolution:
            path,keep=resolution
            if path not in conflicts or path in blocked:raise ValueError('Conflict changed or is not a regular eligible file')
            target='developer' if keep=='chat' else 'chat'
            changes[target][path]=snapshots[keep].get(path);conflicts.remove(path)
        next_base={**{p:h for p,h in base.items() if p in conflicts},**agreed}
        copied=0
        for side,updates in changes.items():
            if not updates:continue
            source='developer' if side=='chat' else 'chat'
            wanted={path for path,digest in updates.items() if digest is not None}
            bundle=await links.browser.read(destinations[source],'export',path=scopes[source],developer=adapters[source]) if wanted else {'files':[]}
            contents={f['path']:f for f in bundle['files'] if f['path'] in wanted}
            patch=[]
            for path,expected in updates.items():
                item=contents.get(path);data=item.get('data') if item else None
                if expected is not None and (data is None or hashlib.sha256(base64.b64decode(data,validate=True)).hexdigest()!=expected):
                    conflicts.append(path)
                    if path in base:next_base[path]=base[path]
                    continue
                patch.append({'path':path,'before':snapshots[side].get(path),'data':data,'mode':item.get('mode',0o600) if item else 0o600})
            if not patch:continue
            result=await links.browser.invoke(destinations[side],(ROOT/'sandbox/sync_project.py').read_text(),{'scope':scopes[side],'changes':patch},adapters[side])
            applied=set(result['applied'])
            for change in patch:
                path=change['path']
                if path in applied:
                    copied+=1
                    if updates[path] is not None:next_base[path]=updates[path]
                else:
                    conflicts.append(path)
                    if path in base:next_base[path]=base[path]
        conflicts=sorted(set(conflicts))
        status={**(p.get('workspace_sync') or {}),'direction':'to_chat','path':paths[0],
                'chat_source_path':paths[0],'developer_source_path':paths[1],
                'state':'conflict' if conflicts else 'synced','conflicts':conflicts[:20],
                'conflict_count':len(conflicts),'file_count':len(next_base),'copied':copied,'at':time.time()}
        status.pop('source_digest',None);status.pop('error',None)
        with store.db:
            store.db.execute('INSERT INTO source_sync_state VALUES (?,?) ON CONFLICT(project) DO UPDATE SET body=excluded.body',(p['id'],json.dumps({'binding':binding,'base':next_base})))
            store.db.execute('UPDATE projects SET workspace_sync=? WHERE id=? AND owner=?',(json.dumps(status),p['id'],owner))
        return status

    def failed(self,p):
        status={**(p.get('workspace_sync') or {}),'state':'retrying','error':'Source sync could not complete. Existing files are retained; it will retry.'}
        with self.links.store.db:self.links.store.db.execute('UPDATE projects SET workspace_sync=? WHERE id=?',(json.dumps(status),p['id']))

    async def poll(self):
        links=self.links
        projects=[p for p in links.store.projects('local-owner') if p['workspace_id'] and p['developer_workspace_id'] and not p['archived'] and not p['deleting']]
        if not projects:return
        a,b=await asyncio.gather(links.coder.api('GET','/api/v2/workspaces',params={'q':'owner:me'}),links.developer.api('GET','/api/v2/workspaces',params={'q':'owner:me'}))
        chat={w['id']:w for w in a['workspaces'] if not w.get('deleted') and w['latest_build']['status']=='running'}
        developer={w['id']:w for w in b['workspaces'] if not w.get('deleted') and w['latest_build']['status']=='running'}
        for p in projects:
            if p['workspace_id'] not in chat or p['developer_workspace_id'] not in developer:continue
            lock=links.coder.project_locks.setdefault(p['id'],asyncio.Lock())
            if lock.locked():continue
            try:
                async with lock,links.slots:
                    p=links.project(p['id'],'local-owner');links.idle(p,'local-owner')
                    if chat[p['workspace_id']]['template_id']!=links.coder.settings()['template_id']:raise ValueError('Template mismatch')
                    # Protect only this transfer. Do not mark status polling/sync as
                    # user activity or wake sleeping workspaces.
                    ids={p['workspace_id'],p['developer_workspace_id']}
                    links.coder.provisioning.update(ids)
                    self.background.add(p['id'])
                    try:await self.run(p,'local-owner',chat[p['workspace_id']],developer[p['developer_workspace_id']])
                    finally:
                        self.background.discard(p['id']);links.coder.provisioning.difference_update(ids)
            except Exception as error:
                from fastapi import HTTPException
                # Busy projects are expected; the next pass follows completion.
                if not isinstance(error,HTTPException) or error.status_code!=409:self.failed(p)

    async def maintain(self):
        from .limits import value
        while True:
            self.event.clear()
            try:await self.poll()
            except Exception:pass  # Portal outage: next pass retries, never treats it as empty source.
            try:await asyncio.wait_for(self.event.wait(),value('PROJECT_SYNC_SECONDS'))
            except TimeoutError:pass
