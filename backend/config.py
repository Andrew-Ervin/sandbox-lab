import os
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
load_dotenv(ROOT / 'config/limits.env')
load_dotenv(ROOT / 'config/models.env')
STATE = Path(os.getenv('LAB_STATE_DIR', str(ROOT / '.local')))
STATE.mkdir(exist_ok=True)
MODEL = os.getenv('OPENROUTER_MODEL', 'openai/gpt-5.6-luna')
REASONING = os.getenv('OPENROUTER_REASONING', 'xhigh')
# The gateway does not expose the upstream key.  Operators may list the models
# they have priced and approved for workstations here; Luna is always present
# and remains the default.  A deliberately explicit catalog prevents an
# unpriced model selected in an editor from bypassing the pilot cost ledger.
WORKSPACE_MODELS = tuple(dict.fromkeys(
    [MODEL, *[item.strip() for item in os.getenv('WORKSPACE_MODELS', '').split(',') if item.strip()]]
))
API_KEY = os.getenv('OPENROUTER_API_KEY', '')
DOMAIN_KEY = os.getenv('CHATKIT_DOMAIN_KEY', 'domain_pk_localhost_dev')
