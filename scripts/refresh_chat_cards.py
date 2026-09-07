"""Refresh saved presentation only; retain widget IDs, messages and original files."""
import argparse,json,sqlite3
from backend.store import SQLiteStore
from backend.chat_cards import artifact_card,app_card
from backend.config import STATE
from backend.experiments import experiment

def actions(value):
    if isinstance(value,dict):
        if isinstance(value.get('onClickAction'),dict):yield value['onClickAction']
        for child in value.values():yield from actions(child)
    elif isinstance(value,list):
        for child in value:yield from actions(child)

def refresh(store,apply=False):
    changes=[]
    for key,body,owner in store.db.execute("SELECT i.id,i.body,t.owner FROM items i JOIN threads t ON t.id=i.thread WHERE json_extract(i.body,'$.type')='widget'"):
        value=json.loads(body);card=value.get('widget',{});updated=experiment.rebuild_card(value)
        for action in actions(card):
            if action.get('type') not in ('open_artifact','open_app'):continue
            payload=action.get('payload') or {};run=store.get_run(payload.get('run_id',''),owner)
            if not run:continue
            if action['type']=='open_app':updated=app_card(run);break
            # Existing chart buttons may point at the paired HTML first.
            name=payload.get('name','')
            if name.endswith('.html'):
                png=next((a for a in run.get('artifacts',[]) if a['name']==name[:-5]+'.png' and a.get('inline_png')),None)
                if png:name=png['name']
            artifact=next((a for a in run.get('artifacts',[]) if a['name']==name),None)
            if artifact and (STATE/'artifacts'/run['id']/name).is_file():updated=artifact_card(run,artifact,STATE);break
        if updated:
            value['widget']=updated.model_dump(mode='json',exclude_none=True)
            rendered=json.dumps(value)
            if json.loads(body)!=value:changes.append((rendered,key))
    if apply:
        backup=STATE/'before-chat-card-refresh.db'
        if not backup.exists():
            with sqlite3.connect(backup) as target:store.db.backup(target)
        with store.db:store.db.executemany('UPDATE items SET body=? WHERE id=?',changes)
    return len(changes)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args()
    count=refresh(SQLiteStore(),args.apply)
    print(('Refreshed' if args.apply else 'Would refresh'),count,'saved cards. Message text, widget IDs and artifact files are unchanged.')
