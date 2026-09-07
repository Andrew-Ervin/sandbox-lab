"""Idempotently insert the user-requested, explicitly labelled reference app."""
import asyncio, hashlib, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.config import STATE
from backend.store import SQLiteStore
from chatkit.types import ThreadMetadata,UserMessageItem,UserMessageTextContent,AssistantMessageItem,AssistantMessageContent,WidgetItem
from chatkit.widgets import Card,Text,Button

reference=STATE/'architecture-guide.json'
THREAD=json.loads(reference.read_text())['thread'] if reference.exists() else 'thr_'+hashlib.sha256(b'sandbox-lab-architecture-reference').hexdigest()[:32]
RUN='run_architecture_field_guide'
async def seed():
    store=SQLiteStore();context={'owner':'local-owner'};now=datetime.now(timezone.utc)
    thread=ThreadMetadata(id=THREAD,title='Sandbox Lab — Architecture field guide',created_at=now,metadata={'seeded_reference':True})
    await store.save_thread(thread,context)
    folder=STATE/'artifacts'/RUN;folder.mkdir(parents=True,exist_ok=True)
    files=[(ROOT/'reports/architecture/architecture.html','architecture.html'),(ROOT/'docs/ARCHITECTURE-GUIDE.md','architecture-guide.md'),(ROOT/'docs/ENTERPRISE-HARDENING.md','enterprise-hardening.md'),(ROOT/'docs/AZURE-IMPLEMENTATION.md','azure-implementation.md'),(ROOT/'docs/MANAGED-PI-DESIGN.md','managed-pi-design.md')]
    artifacts=[]
    for source,name in files:
        shutil.copyfile(source,folder/name)
        artifacts.append({'name':name,'url':f'/api/artifact-view/{RUN}/{name}','download_url':f'/api/artifacts/{RUN}/{name}'})
        store.remember_file(THREAD,name,RUN,(folder/name).stat().st_size)
    run={'id':RUN,'thread_id':THREAD,'mode':'app','status':'completed','engine':'reference','pod':'static-architecture-guide','summary':'Interactive map of execution, idle behavior, packages, credentials and storage. Includes the AKS and OneDrive proposals.','preview_artifact':'architecture.html','preview_url':f'/api/app-preview/{RUN}','artifacts':artifacts,'seeded_reference':True}
    store.save_run(run)
    # Retire only our prior integration fixture from the gallery, not a user app.
    fixture=STATE/'pi-app-smoke.json'
    if fixture.exists():
        prior=store.get_run(json.loads(fixture.read_text())['run'],context['owner'])
        if prior:
            prior['gallery_hidden']=True;store.save_run(prior)
    items=[
      UserMessageItem(id='msg_architecture_request',thread_id=THREAD,created_at=now,content=[UserMessageTextContent(text='Reference request: explain how Sandbox Lab execution environments, packages, credentials, app lifetimes and storage work, including the AKS and OneDrive options.')],inference_options={}),
      AssistantMessageItem(id='msg_architecture_answer',thread_id=THREAD,created_at=now,content=[AssistantMessageContent(text='This is a seeded reference conversation inserted at your request. The guide was prepared outside the chat execution pipeline; this is not a recorded model run.\n\nOpen the field guide for a single-pane execution map, an idle-time simulator and detailed sections on packages, Pi/Ori access, storage and AKS. It is a self-contained static app and needs no coding pod. The text guide, enterprise hardening plan, managed Pi design and Azure implementation guide are also in Conversation files. Open the Managed Pi tab for the proposed credential boundary and an interactive request walkthrough.\n\nChat now routes automatically. Quick Python is disposable with local working-file checkpoints; clean quick and Coder reserves remain unassigned until needed. Persistent AI projects and human VS Code workstations have separate homes. Generated app servers currently share their development workspace and stop when it stops. The OpenRouter key stays in trusted services, while developers can read their own limited gateway capability. OneDrive is a proposed checkpoint adapter, not connected storage.')]),
      WidgetItem(id='widget_architecture_app',thread_id=THREAD,created_at=now,widget=Card(theme='dark',background='surface-secondary',children=[Text(value='Your app is ready'),Text(value='Sandbox Lab — Architecture field guide'),Button(label='Open app',onClickAction={'type':'open_app','handler':'client','payload':{'run_id':RUN}})])),
    ]
    for item in items: await store.save_item(THREAD,item,context)
    (STATE/'architecture-guide.json').write_text(json.dumps({'thread':THREAD,'run':RUN,'preview':run['preview_url']},indent=2))
    print(json.dumps({'thread':THREAD,'run':RUN,'apps':len(store.apps(context['owner']))}))

if __name__=='__main__':asyncio.run(seed())
