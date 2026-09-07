"""Configure workspace package managers for the central read-only gateway."""
from pathlib import Path
import re
BASE='http://package-proxy.lab-control.svc.cluster.local:3128'
def configure():
    home=Path.home()
    def write(name,value):
        p=home/name;p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists() and not p.with_name(p.name+'.before-lab').exists():p.with_name(p.name+'.before-lab').write_bytes(p.read_bytes())
        p.write_text(value)
    write('.config/uv/uv.toml',f'index-url = "{BASE}/python/simple/"\nallow-insecure-host = ["package-proxy.lab-control.svc.cluster.local"]\n# The central gateway enforces release age and explicit human exceptions.\n')
    # The gateway is authoritative even if a user changes these preferences.
    write('.npmrc',f'registry={BASE}/npm/\naudit=false\nfund=false\nfetch-retries=1\n')
    write('.cargo/config.toml',f'[source.crates-io]\nreplace-with = "lab"\n[source.lab]\nregistry = "sparse+{BASE}/cargo/index/"\n[build]\njobs = 2\n')
    write('.config/go/env',f'GOPROXY={BASE}/go\nGOSUMDB=sum.golang.org\nGOTOOLCHAIN=local\n')
    write('.nuget/NuGet/NuGet.Config',f'<?xml version="1.0"?><configuration><packageSources><clear/><add key="lab" value="{BASE}/nuget/v3/index.json" allowInsecureConnections="true"/></packageSources></configuration>')
    values=f'\n# Sandbox Lab package policy\nexport JULIA_PKG_SERVER="{BASE}/julia"\nexport UV_INDEX_URL="{BASE}/python/simple/"\nexport UV_INSECURE_HOST="package-proxy.lab-control.svc.cluster.local"\n'
    for name in ['.profile','.bashrc']:
        p=home/name;old=p.read_text() if p.exists() else ''
        old=re.sub(r'\n# Sandbox Lab package policy\n(?:export [^\n]*\n)*','',old)
        p.write_text(old+values)
if __name__=='__main__':configure()
