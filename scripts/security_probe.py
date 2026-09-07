"""Live tests of the local cluster; never executes a host shell from model output."""
import asyncio,json,time
from backend.compute import compute
CODE='''import os,socket,json,pathlib
r={"uid":os.getuid(),"service_account_token":pathlib.Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists(),"docker_socket":pathlib.Path("/var/run/docker.sock").exists(),"openrouter_key":bool(os.getenv("OPENROUTER_API_KEY"))}
try:
 pathlib.Path("/etc/lab-write-probe").write_text("x"); r["rootfs_writable"]=True
except OSError: r["rootfs_writable"]=False
for name,host,port in [("internet","1.1.1.1",443),("metadata","169.254.169.254",80),("kubernetes","10.96.0.1",443),("node","172.18.0.2",10250)]:
 s=socket.socket(); s.settimeout(1)
 try: s.connect((host,port)); r[name+"_reachable"]=True
 except OSError: r[name+"_reachable"]=False
 finally: s.close()
print(json.dumps(r))'''
async def main():
    pod=await compute.acquire()
    try:
        out=json.loads(await compute.execute(pod,['python','/opt/lab/quick.py'],{'code':CODE}))
        result=json.loads(out['stdout'])
        assert result['uid']==1000
        assert all(v is False for k,v in result.items() if k!='uid'),result
        print(json.dumps({'quick_isolation':result,'pod':pod},indent=2))
    finally: await compute.call('delete_namespaced_pod',pod,'lab-sandboxes')
asyncio.run(main())
