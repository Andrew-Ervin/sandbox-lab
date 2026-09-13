"""Per-user portable editor preferences with per-workspace merge baselines."""
import asyncio
import json
import time
from .config import ROOT

class EditorProfiles:
    def __init__(self, control):
        self.control=control;self.locks={}
        control.db.executescript('CREATE TABLE IF NOT EXISTS editor_profiles(owner TEXT PRIMARY KEY, body TEXT NOT NULL, updated REAL); CREATE TABLE IF NOT EXISTS editor_baselines(workspace TEXT PRIMARY KEY, body TEXT NOT NULL);')

    def get(self,owner):
        row=self.control.db.execute('SELECT body,updated FROM editor_profiles WHERE owner=?',(owner,)).fetchone()
        return {'profile':json.loads(row[0]),'updated':row[1]} if row else {'profile':None,'updated':None}

    async def command(self,record,payload):
        result=await self.control.execute(record['id'],['python','-I','-c',(ROOT/'sandbox/editor_preferences.py').read_text()],
            stdin=json.dumps(payload),bootstrap=True,timeout=15,maximum=600000)
        if result['exit_code']:raise RuntimeError('Editor preferences could not synchronize')
        return json.loads(result['stdout'])

    def baseline(self,wid,value):
        with self.control.db:self.control.db.execute('INSERT OR REPLACE INTO editor_baselines VALUES (?,?)',(wid,json.dumps(value)))

    async def capture(self,record):
        owner=record.get('owner')
        if not owner or record['kind']!='developer' or record.get('warm'):return
        async with self.locks.setdefault(owner,asyncio.Lock()):
            incoming=await self.command(record,{'action':'export'})
            row=self.control.db.execute('SELECT body FROM editor_baselines WHERE workspace=?',(record['id'],)).fetchone()
            base=json.loads(row[0]) if row else None
            saved=self.get(owner)['profile']
            if saved is None:merged=incoming
            elif base is None:
                # A previously existing environment must not overwrite a newer profile.
                self.baseline(record['id'],incoming);return
            else:
                merged={**saved}
                for field in ('settings','layout'):
                    result={**saved.get(field,{})}
                    for key in set(base.get(field,{}))|set(incoming.get(field,{})):
                        if base.get(field,{}).get(key)!=incoming.get(field,{}).get(key):
                            if key in incoming.get(field,{}):result[key]=incoming[field][key]
                            else:result.pop(key,None)
                    merged[field]=result
                for field in ('keybindings','extensions'):
                    if incoming.get(field)!=base.get(field):merged[field]=incoming.get(field,[])
            if saved!=merged:
                with self.control.db:self.control.db.execute('INSERT OR REPLACE INTO editor_profiles VALUES (?,?,?)',(owner,json.dumps(merged),time.time()))
            self.baseline(record['id'],incoming)

    async def restore(self,record):
        owner=record.get('owner')
        if not owner or record['kind']!='developer' or record.get('warm'):return
        if self.control.db.execute('SELECT 1 FROM editor_baselines WHERE workspace=?',(record['id'],)).fetchone():
            await self.capture(record)
        async with self.locks.setdefault(owner,asyncio.Lock()):
            profile=self.get(owner)['profile']
            if profile is not None:await self.command(record,{'action':'apply','profile':profile})
            self.baseline(record['id'],await self.command(record,{'action':'export'}))
