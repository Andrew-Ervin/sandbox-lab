"""Stop inactive workspace compute; retain all Coder home volumes."""
import asyncio,os,time
from datetime import datetime

def timestamp(value):
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError,AttributeError):return 0

class IdleWorkspaces:
    def __init__(self,coder,developer,previews):
        self.coder=coder;self.developer=developer;self.previews=previews
        self.started=time.time();self.stopped=0;self.error=None
        self.project_idle=float(os.getenv('PROJECT_IDLE_SECONDS','300'))
        self.developer_idle=float(os.getenv('DEVELOPER_IDLE_SECONDS','600'))
    def protected(self,wid):
        return (hasattr(self.coder,'reserve') and self.coder.reserve.protected(wid)) or wid in self.previews.active_workspaces() or wid in self.coder.active or wid in getattr(self.coder,'provisioning',set())
    async def reap(self):
        for adapter,seconds in [(self.coder,self.project_idle),(self.developer,self.developer_idle)]:
            result=await adapter.api('GET','/api/v2/workspaces',params={'q':'owner:me'})
            for ws in result.get('workspaces',[]):
                wid=ws['id'];build=ws['latest_build']
                if ws.get('deleted') or build['status']!='running' or self.protected(wid):continue
                if adapter is self.developer and any(not t.done() for k,t in adapter.tasks.items() if k==wid):continue
                # Coder last_used_at includes connections/polls. It is deliberately NOT
                # human activity. A fresh build provides grace for direct portal starts.
                used=max(adapter.touched.get(wid,0),timestamp(build.get('updated_at')),timestamp(ws.get('created_at')))
                if time.time()-used<seconds or time.time()-self.started<30:continue
                if adapter is self.developer and hasattr(adapter,'activity'):
                    used=max(used,await adapter.activity(wid))
                    if time.time()-used<seconds:continue
                if self.protected(wid) or time.time()-adapter.touched.get(wid,0)<seconds:continue
                await adapter.api('POST','/api/v2/workspaces/'+wid+'/builds',json={'transition':'stop'})
                self.stopped+=1
    async def maintain(self):
        while True:
            try:await self.reap();self.error=None
            except Exception:self.error='Workspace idle cleanup will retry.'
            await asyncio.sleep(15)
