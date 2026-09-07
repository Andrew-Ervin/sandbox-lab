import os
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
load_dotenv(ROOT / 'config/limits.env')
load_dotenv(ROOT / 'config/models.env')
STATE = ROOT / '.local'
STATE.mkdir(exist_ok=True)
MODEL = os.getenv('OPENROUTER_MODEL', 'openai/gpt-5.6-luna')
REASONING = os.getenv('OPENROUTER_REASONING', 'xhigh')
API_KEY = os.getenv('OPENROUTER_API_KEY', '')
DOMAIN_KEY = os.getenv('CHATKIT_DOMAIN_KEY', 'domain_pk_localhost_dev')
KUBECONFIG = str(ROOT / '.local' / 'broker-kubeconfig')
NAMESPACE = 'lab-sandboxes'
CODER_URL = 'http://127.0.0.1:7081'
