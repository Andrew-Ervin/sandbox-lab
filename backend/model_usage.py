"""Private, owner-scoped provider accounting; no prompts or credentials retained."""
import json
import math
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def number(value):
    if isinstance(value, bool):return None
    try:
        n=float(value)
        return n if math.isfinite(n) and n>=0 else None
    except (ValueError,TypeError):return None


def extract(content):
    """Read JSON or SSE usage from all three supported provider protocols."""
    text=content.decode('utf-8',errors='replace')
    try:events=[json.loads(text)]
    except ValueError:
        events=[]
        for block in text.replace('\r\n','\n').split('\n\n'):
            data='\n'.join(line[5:].lstrip() for line in block.splitlines() if line.startswith('data:'))
            try:events.append(json.loads(data))
            except ValueError:pass
    usage={};generation=None
    for event in events:
        if not isinstance(event,dict):continue
        for item in (event,event.get('response'),event.get('message')):
            if not isinstance(item,dict):continue
            if isinstance(item.get('id'),str) and item['id'].startswith('gen-'):generation=item['id'][:180]
            if isinstance(item.get('usage'),dict):usage.update(item['usage'])
    details=usage.get('prompt_tokens_details') or usage.get('input_tokens_details') or {}
    cached=number(details.get('cached_tokens')) if isinstance(details,dict) else None
    if cached is None:cached=number(usage.get('cache_read_input_tokens'))
    writes=number(usage.get('cache_creation_input_tokens'))
    if writes is None and isinstance(details,dict):writes=number(details.get('cache_write_tokens'))
    inp=number(usage.get('prompt_tokens',usage.get('input_tokens')))
    # Anthropic input excludes cache reads/writes; OpenAI input includes them.
    if inp is not None and ('cache_read_input_tokens' in usage or 'cache_creation_input_tokens' in usage):inp+=(cached or 0)+(writes or 0)
    return {'generation':generation,'input_tokens':inp,'cached_tokens':cached,'cache_write_tokens':writes,'output_tokens':number(usage.get('completion_tokens',usage.get('output_tokens'))),'cost':number(usage.get('cost'))}


class UsageLedger:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS usage (id TEXT PRIMARY KEY,owner TEXT NOT NULL,at REAL NOT NULL,model TEXT NOT NULL,protocol TEXT NOT NULL,generation TEXT,input_tokens REAL,cached_tokens REAL,cache_write_tokens REAL,output_tokens REAL,cost REAL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS usage_owner_time ON usage(owner,at)');self.db.commit();path.chmod(0o600)
    def record(self,ident,owner,model,protocol,content,at=None):
        u=extract(content)
        self.db.execute('INSERT OR IGNORE INTO usage VALUES (?,?,?,?,?,?,?,?,?,?,?)',(ident,owner,at if at is not None else time.time(),model,protocol,u['generation'],u['input_tokens'],u['cached_tokens'],u['cache_write_tokens'],u['output_tokens'],u['cost']));self.db.commit()
    def summary(self,owner,now=None):
        now=now or datetime.now(timezone.utc);day=now.replace(hour=0,minute=0,second=0,microsecond=0)
        starts={'today':day,'week':day-timedelta(days=day.weekday()),'month':day.replace(day=1),'year':day.replace(month=1,day=1)}
        periods={}
        for name,start in starts.items():
            row=self.db.execute('SELECT count(*),count(cost),sum(cost),sum(input_tokens),sum(cached_tokens),sum(cache_write_tokens),sum(output_tokens) FROM usage WHERE owner=? AND at>=? AND at<=?',(owner,start.timestamp(),now.timestamp())).fetchone()
            periods[name]=dict(zip(('requests','priced_requests','cost','input_tokens','cached_tokens','cache_write_tokens','output_tokens'),row))
            periods[name]['pending_requests']=row[0]-row[1]
        first=self.db.execute('SELECT min(at) FROM usage WHERE owner=?',(owner,)).fetchone()[0]
        return {'periods':periods,'timezone':'UTC','week_starts':'Monday','tracking_since':first,'observed_at':now.timestamp(),'scope':'All workspace coding tools using this broker, for your account. Historical traffic before tracking is not included.'}

_ledger=None
def ledger():
    global _ledger
    if _ledger is None:
        from .config import STATE
        _ledger=UsageLedger(STATE/'model-usage.sqlite')
    return _ledger

async def reconcile(owner,limit=10):
    """Best-effort delayed lookup; never replay inference to recover accounting."""
    import httpx
    from .config import API_KEY
    l=ledger();l.db.execute('CREATE TABLE IF NOT EXISTS usage_checks (id TEXT PRIMARY KEY,at REAL,attempts INTEGER)')
    rows=l.db.execute('SELECT u.id,u.generation FROM usage u LEFT JOIN usage_checks c ON c.id=u.id WHERE u.owner=? AND u.cost IS NULL AND u.generation IS NOT NULL AND u.at<? AND (c.id IS NULL OR (c.at<? AND c.attempts<3)) ORDER BY u.at LIMIT ?', (owner,time.time()-5,time.time()-300,limit)).fetchall()
    if not rows:return
    async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
        for ident,generation in rows:
            l.db.execute('INSERT INTO usage_checks VALUES (?,?,1) ON CONFLICT(id) DO UPDATE SET at=excluded.at,attempts=attempts+1',(ident,time.time()));l.db.commit()
            try:
                r=await client.get('https://openrouter.ai/api/v1/generation',params={'id':generation},headers={'Authorization':'Bearer '+API_KEY});r.raise_for_status();d=r.json()['data']
                cost=number(d.get('total_cost'))
                # Some incomplete records return all-zero counters. Only accept
                # completed metadata or an explicit response-cache indicator.
                if cost is None or not (d.get('finish_reason') or d.get('native_finish_reason') or d.get('response_cache_source_id')):continue
                values=[number(d.get(k)) for k in ('native_tokens_prompt','native_tokens_cached','native_tokens_completion')]
                l.db.execute('UPDATE usage SET cost=?,input_tokens=COALESCE(?,input_tokens),cached_tokens=COALESCE(?,cached_tokens),output_tokens=COALESCE(?,output_tokens) WHERE id=? AND owner=?',(cost,*values,ident,owner));l.db.commit()
            except (httpx.HTTPError,ValueError,KeyError,TypeError):pass

_pending=set()
def schedule_reconciliation(owner):
    import asyncio
    if owner in _pending:return
    _pending.add(owner)
    async def run():
        try:await reconcile(owner)
        finally:_pending.discard(owner)
    task=asyncio.create_task(run())
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
