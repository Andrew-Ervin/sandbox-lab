"""Background infrastructure health, never a prerequisite for browsing saved work."""
import asyncio
import time

class HealthCache:
    def __init__(self,ttl=5):
        self.ttl=ttl;self.expires=0;self.value=None;self.task=None

    async def get(self,compute,headless):
        if time.monotonic()>=self.expires and (self.task is None or self.task.done()):
            self.task=asyncio.create_task(self.refresh(compute,headless))
        return {**(self.value or {'provider':'azure','azure':False,'warm_pods':0,'headless':False}),
                'health_refreshing':bool(self.task and not self.task.done())}

    async def refresh(self,compute,headless):
        pods,ready=await asyncio.gather(compute.pool(),headless.ready(),return_exceptions=True)
        self.value={'provider':'azure','azure':compute.ready and not isinstance(pods,BaseException) and not isinstance(ready,BaseException) and bool(ready),
                    'warm_pods':0 if isinstance(pods,BaseException) else len(pods),'headless':False if isinstance(ready,BaseException) else bool(ready)}
        self.expires=time.monotonic()+self.ttl
