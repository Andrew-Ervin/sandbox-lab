"""Cache shared infrastructure health, never owner data or credentials."""
import asyncio
import time

class HealthCache:
    def __init__(self,ttl=5):
        self.ttl=ttl; self.expires=0; self.value=None; self.lock=asyncio.Lock()

    async def get(self,compute,coder):
        if self.value is not None and time.monotonic()<self.expires: return dict(self.value)
        async with self.lock:
            if self.value is not None and time.monotonic()<self.expires: return dict(self.value)
            pods,coder_ready=await asyncio.gather(compute.pool(),coder.ready(),return_exceptions=True)
            self.value={'kubernetes':compute.ready and not isinstance(pods,BaseException),
                        'warm_pods':0 if isinstance(pods,BaseException) else len(pods),
                        'coder':False if isinstance(coder_ready,BaseException) else bool(coder_ready)}
            self.expires=time.monotonic()+self.ttl
            return dict(self.value)
