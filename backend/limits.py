"""Public, bounded operational limits. Never forward the operator environment."""
import json,os
from .config import ROOT
from dotenv import dotenv_values

KEYS=tuple(dotenv_values(ROOT/'config/limits.env'))
def value(name):return int(os.environ[name])
def sandbox_environment():
    return {k:os.environ[k] for k in KEYS if k.startswith(('SYNC_','ARTIFACT_','QUICK_CODE_','QUICK_CPU_','QUICK_RUN_','QUICK_STDOUT_'))}
def script_with_limits(script):
    return 'import os; os.environ.update('+repr(sandbox_environment())+')\n'+script

def validate():
    for name in KEYS:
        if name.endswith('_QUOTA'):continue
        number=value(name)
        if number<0 or (number==0 and name not in ('WARM_POOL_SIZE','WARM_POOL_MAX','PROJECT_WARM_RESERVE')):
            raise ValueError(name+' must be positive (warm reserves may be zero)')
    if value('DICTATION_MAX_BYTES')<44+(value('DICTATION_MAX_SECONDS')+2)*32000:
        raise ValueError('DICTATION_MAX_BYTES must fit mono 16 kHz PCM WAV plus two seconds of recorder tolerance')
    if value('BROKER_RENEW_BEFORE_SECONDS')>=value('BROKER_TOKEN_SECONDS'):raise ValueError('Broker renewal margin must be shorter than token lifetime')
    if value('WORKSPACE_TOKEN_RENEW_BEFORE_SECONDS')>=3600:raise ValueError('Workspace renewal margin must be less than one hour')
    if value('QUICK_MAX_PODS')<value('QUICK_CONCURRENCY'):raise ValueError('QUICK_MAX_PODS must cover QUICK_CONCURRENCY')
    for prefix in ('SYNC','ARTIFACT'):
        if value(prefix+'_MAX_TOTAL_BYTES')<value(prefix+'_MAX_FILE_BYTES'):raise ValueError(prefix+' total must fit a file')
