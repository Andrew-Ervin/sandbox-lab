import json
from pathlib import Path
import pytest
from backend.documentation import read_documentation,MAX_RESULT
from backend.approval_cards import approval_card
from backend.store import SQLiteStore
from chatkit.types import ThreadMetadata
from datetime import datetime,timezone


def test_documentation_is_bounded_curated_and_contains_no_secrets(tmp_path,monkeypatch):
    (tmp_path/'docs').mkdir();(tmp_path/'docs/SCALING.md').write_text('# Scaling\n'+('queues and capacity\n'*20000))
    (tmp_path/'.env').write_text('PRIVATE_VALUE')
    monkeypatch.setenv('OPENROUTER_API_KEY','PRIVATE_VALUE')
    result=read_documentation('scaling','capacity',root=tmp_path)
    assert sum(len(e['text']) for e in result['excerpts'])<=MAX_RESULT
    assert 'PRIVATE_VALUE' not in json.dumps(result)
    with pytest.raises(ValueError):read_documentation('../.env',root=tmp_path)
    (tmp_path/'docs/SCALING.md').unlink();(tmp_path/'docs/SCALING.md').symlink_to(tmp_path/'.env')
    assert read_documentation('scaling',root=tmp_path)['excerpts']==[]


def test_approval_summary_keeps_decision_bound_to_exact_action_and_full_request_link():
    action={'type':'approval_decide','handler':'client','payload':{'proposal_id':'p','action_hash':'hash'}}
    card=approval_card(title='Request',fields=[('To','test@example.invalid')],body='Long body. '*700,thread_id='t',item_id='i',action=action)
    data=card.model_dump(mode='json',exclude_none=True)
    assert data['confirm']['action']['payload']=={'proposal_id':'p','action_hash':'hash','decision':'approve'}
    assert data['cancel']['action']['payload']['decision']=='reject'
    assert len(json.dumps(data))<4500
    assert data['children'][-1]['children'][0]['onClickAction']['payload']=={'thread_id':'t','item_id':'i'}
    complete=approval_card(title='Request',fields=[],body='done',thread_id='t',item_id='i',decision='Approved')
    assert complete.collapsed and complete.confirm is None and complete.cancel is None


@pytest.mark.asyncio
async def test_dashboard_projection_omits_large_execution_details_but_preserves_saved_run(tmp_path,monkeypatch):
    store=SQLiteStore(tmp_path/'db');thread=ThreadMetadata(id='t',created_at=datetime.now(timezone.utc))
    await store.save_thread(thread,{'owner':'a'})
    run={'id':'r','thread_id':'t','mode':'app','status':'completed','preview_url':'/api/app-preview/r','code':'x'*1_000_000,'output':'y'*1_000_000,'executions':[{'code':'secret source'}]}
    store.save_run(run)
    original=json.loads
    def bounded(body,*args,**kwargs):
        assert len(body)<10_000,'Dashboard decoded unneeded execution content'
        return original(body,*args,**kwargs)
    monkeypatch.setattr(json,'loads',bounded)
    assert 'code' not in store.runs('a',details=False)[0]
    assert 'output' not in store.apps('a')[0]
    assert store.runs('b',details=False)==[] and store.apps('b')==[]
    monkeypatch.setattr(json,'loads',original)
    assert store.get_run('r','a')['code']==run['code']


def test_old_active_jobs_stay_visible_after_many_newer_completions(tmp_path):
    store=SQLiteStore(tmp_path/'db')
    store.save_job({'id':'active','thread_id':'t','owner':'a','status':'running','started':1})
    for i in range(150):store.save_job({'id':str(i),'thread_id':'t','owner':'a','status':'completed','started':i+2})
    store.save_job({'id':'other','thread_id':'t','owner':'b','status':'running','started':200})
    jobs=store.jobs('a')
    assert jobs[0]['id']=='active' and len(jobs)==100 and all(j['owner']=='a' for j in jobs)

@pytest.mark.asyncio
async def test_provider_error_in_success_status_is_safe_and_actionable(tmp_path,monkeypatch):
    import httpx
    import backend.chat as module
    monkeypatch.setattr(module,'API_KEY','test-only')
    chat=module.LabChat(SQLiteStore(tmp_path/'db'))
    chat.http=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'error':{'code':503,'message':'PRIVATE_PAYLOAD'}})))
    with pytest.raises(RuntimeError,match='provider could not complete') as error:
        await chat.completion([{'role':'user','content':'test'}])
    assert '503' in str(error.value) and 'PRIVATE_PAYLOAD' not in str(error.value)
    await chat.close()

@pytest.mark.asyncio
async def test_approval_payload_view_requires_owned_saved_item(tmp_path,monkeypatch):
    import httpx
    import backend.main as module
    from chatkit.types import WidgetItem
    from chatkit.widgets import Card,Text
    store=SQLiteStore(tmp_path/'db');now=datetime.now(timezone.utc)
    for tid,owner in [('mine','local-owner'),('other','other-owner')]:
        await store.save_thread(ThreadMetadata(id=tid,created_at=now),{'owner':owner})
        await store.save_item(tid,WidgetItem(id=tid+'-card',thread_id=tid,created_at=now,widget=Card(children=[Text(value='Review')]),copy_text='{"body":"<script>untrusted</script>"}'),{'owner':owner})
    monkeypatch.setattr(module,'store',store)
    received=[]
    async def document(key,name,raw):received.append(raw);return 'http://127.0.0.1:12345/'
    monkeypatch.setattr(module.previews,'document',document)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://127.0.0.1:8787') as c:
        assert (await c.get('/api/approval-payload/mine/mine-card')).status_code==401
        await c.post('/api/bootstrap')
        assert (await c.get('/api/approval-payload/other/other-card')).status_code==404
        assert (await c.get('/api/approval-payload/mine/other-card')).status_code==404
        assert (await c.get('/api/approval-payload/mine/mine-card')).status_code==200
    assert received==[b'{"body":"<script>untrusted</script>"}']


def test_full_json_payload_view_wraps_and_escapes():
    from backend.file_view import render
    html=render(b'{"body":"<script>hello</script>"}','Full request.json').decode()
    assert 'JSON payload' in html and '&lt;script&gt;' in html
    assert 'white-space:pre-wrap;overflow-wrap:anywhere' in html
    assert '<script>hello</script>' not in html
