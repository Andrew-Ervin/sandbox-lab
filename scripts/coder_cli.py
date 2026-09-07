"""Pass Coder credentials through a child environment, never shell arguments."""
import os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ai='--ai' in sys.argv
if ai: sys.argv.remove('--ai')
env=dict(os.environ,CODER_URL='http://127.0.0.1:'+('7081' if ai else '7080'),CODER_SESSION_TOKEN=(root/'.local'/('coder-ai-admin-token' if ai else 'coder-admin-token')).read_text().strip(),CODER_CONFIG_DIR=str(root/'.local/coder-cli'),CODER_USE_KEYRING='false')
p=subprocess.run([str(root/'.local/bin/coder'),*sys.argv[1:]],env=env)
sys.exit(p.returncode)
