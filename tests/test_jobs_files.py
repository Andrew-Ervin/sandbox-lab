import asyncio, json
from datetime import datetime, timezone
import pytest
from chatkit.types import ThreadMetadata
from backend.chat import LabChat
from backend.jobs import Jobs
from backend.store import SQLiteStore
from backend.files import inputs

@pytest.mark.asyncio
async def test_two_chatkit_threads_finish_after_navigation(tmp_path, monkeypatch):
    store=SQLiteStore(tmp_path/'db'); chat=LabChat(store); jobs=Jobs(store)
    gate=asyncio.Event(); entered=0
    async def completion(messages,tools=True):
        nonlocal entered
        entered+=1
        await gate.wait()
        return {'role':'assistant','content':'Finished '+messages[-1]['content']}
    monkeypatch.setattr(chat,'completion',completion)
    contexts=[]; subscribers=[]
    for name in ['A','B']:
        context={'owner':'local-owner','mode':'auto'}; contexts.append(context)
        body=json.dumps({'type':'threads.create','params':{'input':{'content':[{'type':'input_text','text':name}],'attachments':[],'inference_options':{}}}}).encode()
        result=await chat.process(body,context)
        sub=jobs.start(result,context); subscribers.append(sub)
        await anext(sub)
    for _ in range(100):
        if entered==2: break
        await asyncio.sleep(.01)
    assert entered==2
    # Navigating away from both threads closes only their HTTP subscriptions.
    for sub in subscribers: await sub.aclose()
    assert len(jobs.tasks)==2
    gate.set()
    await asyncio.gather(*list(jobs.tasks.values()))
    for context,name in zip(contexts,['A','B']):
        job=context['job']; assert job['status']=='completed'
        page=await store.load_thread_items(job['thread_id'],None,20,'asc',context)
        assert any(item.type=='assistant_message' and item.content[0].text=='Finished '+name for item in page.data)

@pytest.mark.asyncio
async def test_stop_only_cancels_selected_owner_and_thread(tmp_path):
    store=SQLiteStore(tmp_path/'db'); jobs=Jobs(store); gate=asyncio.Event()
    async def stream():
        yield b'data: {}\n\n'
        await gate.wait()
    a=jobs.start(stream(),{'owner':'alice'},'A'); b=jobs.start(stream(),{'owner':'bob'},'B')
    await anext(a); await anext(b)
    await jobs.stop('bob','A'); assert len(jobs.tasks)==2
    await jobs.stop('alice','A'); assert len(jobs.tasks)==1
    gate.set(); await asyncio.gather(*list(jobs.tasks.values()))
    assert store.jobs('alice')[0]['status']=='canceled'
    assert store.jobs('bob')[0]['status']=='completed'

@pytest.mark.asyncio
async def test_file_versions_are_separate_and_older_runs_remain_accessible(tmp_path,monkeypatch):
    import backend.files as module
    monkeypatch.setattr(module,'STATE',tmp_path)
    store=SQLiteStore(tmp_path/'db'); ctx={'owner':'alice'}
    for name in ['A','B']:
        await store.save_thread(ThreadMetadata(id=name,created_at=datetime.now(timezone.utc)),ctx)
        run={'id':'run_'+name,'thread_id':name,'status':'completed'}; store.save_run(run)
        folder=tmp_path/'artifacts'/run['id']; folder.mkdir(parents=True)
        (folder/'data.txt').write_text(name)
        store.remember_file(name,'data.txt',run['id'],1)
    assert inputs(store,'A',['data.txt'])[0]['data']=='QQ=='
    assert inputs(store,'B',['data.txt'])[0]['data']=='Qg=='
    with pytest.raises(ValueError): inputs(store,'A',['other.txt'])
    for i in range(65): store.save_run({'id':f'r{i}','thread_id':'A','status':'completed'})
    assert store.get_run('run_A','alice')
    assert store.get_run('run_A','bob') is None

def test_recovery_marks_interrupted_without_replaying_code(tmp_path):
    store=SQLiteStore(tmp_path/'db')
    store.save_job({'id':'j','owner':'alice','thread_id':'a','status':'running','started':1})
    store.recover_jobs()
    assert store.jobs('alice')[0]['status']=='interrupted'

def test_widget_keeps_client_action_and_embeds_png(tmp_path,monkeypatch):
    import backend.chat as module
    monkeypatch.setattr(module,'STATE',tmp_path)
    folder=tmp_path/'artifacts'/'run_chart';folder.mkdir(parents=True)
    (folder/'chart.png').write_bytes(b'\x89PNG\r\n\x1a\n'+b'\0'*8+(1200).to_bytes(4,'big')+(800).to_bytes(4,'big'))
    chat=LabChat(SQLiteStore(':memory:'))
    thread=ThreadMetadata(id='t',created_at=datetime.now(timezone.utc))
    widget=chat.artifact_widget(thread,{'id':'run_chart'},{'name':'chart.png','inline_png':True}).model_dump()['widget']
    assert widget['theme']=='dark'
    assert widget['children'][1]['aspectRatio']==1.5
    assert widget['children'][1]['src'].startswith('data:image/png;base64,')
    buttons=widget['children'][-1]['children']
    assert {b['onClickAction']['type'] for b in buttons}=={'open_artifact','download_artifact'}
    assert all(b['onClickAction']['handler']=='client' and b['onClickAction']['payload']['run_id']=='run_chart' for b in buttons)
