"""Verified seven-day home archives; native snapshots are not Blob exports."""
import asyncio
import base64
import hashlib
import json
import shlex
import time
import uuid
from pathlib import Path

CHUNK=8_000_000
MAX_BYTES=600_000_000

class AzureArchive:
    def __init__(self,runtime):self.runtime=runtime;self.task=None

    def eligible(self,record):
        return (self.runtime.config.get('archive_after_days')==7 and self.runtime.storage.enabled
                and record['kind'] in ('headless','developer') and record['state']=='stopped'
                and not record.get('warm') and not record.get('disposable') and record.get('sandbox_id')
                and not record.get('cold_archive') and record['id'] not in self.runtime.resizing
                and time.time()-record.get('last_activity_at',record.get('updated_at',time.time()))>=7*86400
                and record.get('archive_retry_at',0)<=time.time())

    def schedule(self):
        if self.task and not self.task.done():return
        if self.runtime.budget.status()['blocked']:return
        record=next((r for r in self.runtime.records() if self.eligible(r)),None)
        if record:self.task=asyncio.create_task(self.archive(record['id']))

    async def upload(self,wid,path):
        size=path.stat().st_size
        if not 0<size<=MAX_BYTES:raise RuntimeError('Home exceeds the cold archive limit; original retained')
        version=uuid.uuid4().hex;chunks=[];digest=hashlib.sha256()
        with path.open('rb') as source:
            while data:=source.read(CHUNK):
                digest.update(data);key=f'home:{wid}:{version}:{len(chunks)}'
                await self.runtime.storage.save('workspaces',key,{'data':base64.b64encode(data).decode()})
                chunks.append({'key':key,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        manifest={'version':1,'workspace':wid,'bytes':size,'sha256':digest.hexdigest(),'chunks':chunks,'created_at':time.time()}
        key=f'home:{wid}:{version}:manifest'
        await self.runtime.storage.save('workspaces',key,manifest)
        # Read every byte back using conditional Blob reads before deleting compute.
        verify=path.with_suffix('.verify')
        try:await self.download(wid,key,verify)
        finally:verify.unlink(missing_ok=True)
        return key

    async def download(self,wid,key,path):
        manifest=await self.runtime.storage.load('workspaces',key)
        if not manifest or manifest.get('version')!=1 or manifest.get('workspace')!=wid:raise RuntimeError('Invalid home archive')
        size=manifest.get('bytes',0);chunks=manifest.get('chunks',[])
        if not 0<size<=MAX_BYTES or len(chunks)!=(size+CHUNK-1)//CHUNK:raise RuntimeError('Invalid archive size')
        digest=hashlib.sha256();total=0
        with path.open('xb') as output:
            path.chmod(0o600)
            for chunk in chunks:
                payload=await self.runtime.storage.load('workspaces',chunk['key'])
                data=base64.b64decode(payload['data'],validate=True)
                if len(data)!=chunk['bytes'] or len(data)>CHUNK or hashlib.sha256(data).hexdigest()!=chunk['sha256']:raise RuntimeError('Archive segment verification failed')
                total+=len(data)
                if total>size:raise RuntimeError('Archive exceeded declared size')
                digest.update(data);output.write(data)
        if total!=size or digest.hexdigest()!=manifest['sha256']:raise RuntimeError('Home archive verification failed')

    async def restore(self,record):
        root=self.runtime.root/'home-transfers';root.mkdir(exist_ok=True,mode=0o700)
        local=root/(record['id']+'-'+uuid.uuid4().hex+'.tgz')
        try:await self.download(record['id'],record['cold_archive'],local)
        except BaseException:
            local.unlink(missing_ok=True);raise
        record['home_restore']=str(local);self.runtime.save(record)

    async def freeze(self,record,stop):
        # Freeze only existing sandbox-user processes. The broker relay and the
        # subsequently launched archive command are unaffected. No guest code is root.
        code="""import os,signal
from pathlib import Path
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  if p.stat().st_uid==1000:os.kill(int(p.name),signal.SIGSTOP if STOP else signal.SIGCONT)
 except (ProcessLookupError,FileNotFoundError,PermissionError):pass
""".replace('if STOP', 'if '+repr(stop))
        await self.runtime.root_exec(record,'python -I -c '+shlex.quote(code))

    async def archive(self,wid):
        runtime=self.runtime
        async with runtime.workspace_locks.setdefault(wid,asyncio.Lock()):
            record=runtime.record(wid)
            if not self.eligible(record):return
            try:remote=await runtime.transport.call('get',runtime.profile(record['kind'])['group'],record['sandbox_id'])
            except Exception:
                record['archive_retry_at']=time.time()+86400;runtime.save(record)
                runtime.telemetry.event(record['kind'],wid,'home_archive_failed',error='Could not verify suspended state; original retained')
                return
            if remote['state'] not in ('Stopped','Suspended'):return
            last=record.get('last_activity_at',record['updated_at'])
            runtime.resizing.add(wid);frozen=False
            try:
                await runtime._start(record)
                record=runtime.record(wid)
                record['archive_frozen']=True;runtime.save(record)
                await self.freeze(record,True);frozen=True
                root=runtime.root/'home-transfers';root.mkdir(exist_ok=True,mode=0o700)
                local=root/(wid+'-'+uuid.uuid4().hex+'.tgz')
                await runtime.export_home(wid,local,'/tmp/lab-home-'+uuid.uuid4().hex+'.parts',require_complete=True)
                key=await self.upload(wid,local)
                await runtime._stop(wid,skip_checkpoint=True)
                frozen=False
                record=runtime.record(wid)
                # Persist recovery information before the potentially ambiguous delete.
                record.update(cold_archive=key,archive_backup=str(local),last_activity_at=last)
                runtime.save(record)
                await runtime.transport.call('delete',runtime.profile(record['kind'])['group'],record['sandbox_id'])
                record.setdefault('previous_sandboxes',[]).append(record['sandbox_id'])
                record.update(sandbox_id=None,create_submitted=False,prepared=False,state='stopped',archived_at=time.time(),archive_frozen=False)
                runtime.save(record)
                runtime.telemetry.event(record['kind'],wid,'home_archived')
            except BaseException as error:
                if frozen:
                    try:await self.freeze(runtime.record(wid),False)
                    except Exception:pass
                try:await runtime._stop(wid)
                except Exception:pass
                record=runtime.record(wid);record.update(archive_retry_at=time.time()+86400,last_activity_at=last,storage_error='Cold archive needs attention; recovery state retained')
                runtime.save(record);runtime.telemetry.event(record['kind'],wid,'home_archive_failed',error=str(error))
                if isinstance(error,asyncio.CancelledError):raise
            finally:runtime.resizing.discard(wid)

    async def close(self):
        # Let an in-flight bounded archival operation reach a safe state before shutdown.
        if self.task:await self.task
