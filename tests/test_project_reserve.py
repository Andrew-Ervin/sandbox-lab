import asyncio,time
from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from chatkit.types import ThreadMetadata
from backend.reserve import ProjectReserve
from backend.store import SQLiteStore

@pytest.mark.asyncio
async def test_clean_reserve_claimed_once_and_idle_drain_preserves_used_home(tmp_path):
    store=SQLiteStore(tmp_path/'db');workspaces={};calls=[]
    async def api(method,path,**kw):
        calls.append((method,path,kw))
        if method=='GET' and path=='/api/v2/workspaces':return {'workspaces':list(workspaces.values())}
        if method=='GET' and '/templates/' in path:return {'active_version_id':'v'}
        if method=='GET':return workspaces[path.rsplit('/',1)[-1]]
        if path.endswith('/builds'):
            wid=path.split('/')[-2];workspaces[wid]['latest_build']['status']='stopped' if kw['json']['transition']=='stop' else 'running';return {}
        wid='w'+str(len(workspaces)+1)
        workspaces[wid]={'id':wid,'name':kw['json']['name'],'template_id':'t','latest_build':{'status':'running','resources':[{'agents':[{'status':'connected'}]}]}}
        return workspaces[wid]
    c=SimpleNamespace(api=api,provision_lock=asyncio.Lock(),max_running=4,touched={},settings=lambda:{'template_id':'t','organization_id':'o'})
    reserve=ProjectReserve(c,tmp_path/'reserve.json');reserve.request();await reserve.reconcile(store)
    assert reserve.state=='ready' and reserve.record['workspace_id']=='w1'
    assert store.db.execute('SELECT COUNT(*) FROM threads').fetchone()[0]==0
    thread=ThreadMetadata(id='a',created_at=datetime.now(timezone.utc));await store.save_thread(thread,{'owner':'a'})
    async with c.provision_lock:assert await reserve.claim(thread,store,{'owner':'a'})=='w1'
    assert reserve.record.get('workspace_id') is None
    assert (await store.load_thread('a',{'owner':'a'})).metadata['coder_workspace_id']=='w1'
    await reserve.reconcile(store);assert reserve.record['workspace_id']=='w2'
    reserve.record['until']=0;await reserve.reconcile(store)
    assert workspaces['w2']['latest_build']['status']=='stopped' and workspaces['w1']['latest_build']['status']=='running'
    # A restart between attaching a home and clearing the ledger cannot recycle it.
    reserve.record['workspace_id']='w1';await reserve.reconcile(store)
    assert not reserve.record.get('workspace_id') and workspaces['w1']['latest_build']['status']=='running'
    assert all(kw.get('json',{}).get('transition')!='delete' for _,_,kw in calls)

@pytest.mark.asyncio
async def test_speculative_warmup_never_evicts_a_full_project_pool(tmp_path):
    store=SQLiteStore(tmp_path/'db');calls=[]
    async def api(method,path,**kw):
        calls.append(method);return {'workspaces':[{'template_id':'t','latest_build':{'status':'running'}}]}
    c=SimpleNamespace(api=api,provision_lock=asyncio.Lock(),max_running=1,touched={},settings=lambda:{'template_id':'t','organization_id':'o'})
    reserve=ProjectReserve(c,tmp_path/'reserve.json');reserve.request();await reserve.reconcile(store)
    assert reserve.state=='capacity full' and calls==['GET'] and not reserve.record.get('workspace_id')
