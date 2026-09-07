"""Demand-based warm reserve. Pure policy so scale-down and burst behavior are testable."""
from collections import deque
import math,time

class WarmPolicy:
    def __init__(self,base=2,maximum=4,idle_seconds=300,clock=time.monotonic):
        self.base=base;self.maximum=maximum;self.idle_seconds=idle_seconds;self.clock=clock
        self.last_activity=None;self.arrivals=deque();self.refill_seconds=1.;self.warm_until=0.
    def touch(self): self.last_activity=self.clock()
    def arrival(self):
        self.touch();self.arrivals.append(self.last_activity)
    def warm(self,seconds=300): self.warm_until=self.clock()+seconds;self.touch()
    def observe_refill(self,seconds): self.refill_seconds=.8*self.refill_seconds+.2*min(60,max(.05,seconds))
    def reserve(self,busy=0):
        now=self.clock()
        while self.arrivals and self.arrivals[0]<now-30: self.arrivals.popleft()
        if not busy and now>=self.warm_until and (self.last_activity is None or now-self.last_activity>=self.idle_seconds): return 0
        rate=len(self.arrivals)/max(5,min(30,now-self.arrivals[0]+1)) if self.arrivals else 0
        return min(self.maximum,max(self.base,math.ceil(rate*self.refill_seconds*1.5)))
