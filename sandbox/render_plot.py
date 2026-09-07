"""Export figure data inside the same isolated pod; never run it on the Mac."""
import json, os, stat, sys
from pathlib import Path
import kaleido
name=sys.argv[1]
if not name.startswith('figure-') or not name.endswith('.json') or '/' in name: raise ValueError('Invalid figure name')
fd=os.open(Path('/workspace/plots')/name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(fd,'rb') as f:
    if not stat.S_ISREG(os.fstat(f.fileno()).st_mode): raise ValueError('Not a regular figure')
    raw=f.read(8_000_001)
if len(raw)>8_000_000: raise ValueError('Figure too large')
fig=json.loads(raw)
layout=fig.get('layout',{})
def dimension(name,default):
    value=layout.get(name,default)
    return int(max(320,min(1600,value))) if isinstance(value,(int,float)) else default
kaleido.write_fig_sync(fig,path='/workspace/artifacts/'+name.removesuffix('.json')+'.png',opts={'format':'png','width':dimension('width',1000),'height':dimension('height',600),'scale':2},kopts={'page_generator':kaleido.PageGenerator(mathjax=False),'timeout':12,'n':1})
