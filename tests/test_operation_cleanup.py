import fcntl,os
from sandbox.azure_execute import reconcile

def test_reconcile_preserves_running_and_recent_operations(tmp_path):
 old='a'*32;active='b'*32;recent='c'*32
 for ident in (old,active,recent):
  for suffix in ('request','result'):
   p=tmp_path/(ident+'.'+suffix);p.write_text('data');os.utime(p,(1,1) if ident!=recent else (5000,5000))
 with (tmp_path/(active+'.lock')).open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  reconcile(tmp_path,5000)
  assert not (tmp_path/(old+'.result')).exists()
  assert (tmp_path/(active+'.request')).exists()
  assert (tmp_path/(recent+'.request')).exists()
 reconcile(tmp_path,5000)
 assert not (tmp_path/(active+'.result')).exists()
