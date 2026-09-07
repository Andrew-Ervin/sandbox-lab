"""Apply locally generated AI titles once. Never sends conversation history to a provider."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.store import SQLiteStore
from backend.config import STATE
from backend.titles import clean_title

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--titles',required=True,type=Path);args=parser.parse_args()
    supplied=json.loads(args.titles.read_text());titles={key:clean_title(value) for key,value in supplied.items()}
    store=SQLiteStore();owner='local-owner'
    rows=store.db.execute('SELECT id,body,updated FROM threads WHERE owner=?',(owner,)).fetchall()
    known={r[0] for r in rows}
    if set(titles)-known:raise ValueError('Title file contains an unknown conversation')
    backup=STATE/'titles-before-v1.json'
    if not backup.exists():
        with backup.open('x') as f:json.dump({tid:{'title':json.loads(body).get('title'),'updated':updated} for tid,body,updated in rows},f,indent=2)
        backup.chmod(0o600)
    count=sum(store.set_generated_title(key,owner,title) for key,title in titles.items())
    (STATE/'titles-v1.done').write_text('Applied locally generated titles; no provider request.\n')
    print(f'Updated {count} titles locally; prior titles backed up.');store.db.close()
if __name__=='__main__':main()
