"""Persist user activity independently of Coder connection/health traffic."""
import json,time
from .config import STATE
class Activity(dict):
    def __init__(self,name):
        self.path=STATE/(name+'-activity.json')
        try: super().__init__(json.loads(self.path.read_text()))
        except (OSError,ValueError): super().__init__()
    def __setitem__(self,key,value):
        super().__setitem__(key,min(time.time(),float(value)))
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self));temp.chmod(0o600);temp.replace(self.path)
