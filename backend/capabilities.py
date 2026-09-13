"""Short-lived workspace model access; the upstream API key never leaves the gateway."""
import base64,hashlib,hmac,json,os,secrets,time
from .config import MODEL,REASONING,WORKSPACE_MODELS

def issue(workspace_id,seconds=3600):
    if not isinstance(workspace_id,str) or not 1<=len(workspace_id)<=128: raise ValueError('Invalid workspace')
    if type(seconds) is not int or not 1<=seconds<=3600: raise ValueError('Invalid capability bounds')
    claims={'aud':'sandbox-lab-model','iat':int(time.time()),'jti':secrets.token_hex(16),'exp':int(time.time())+seconds,'model':MODEL,'models':WORKSPACE_MODELS,'workspace':workspace_id}
    from .workspace_models import snapshot, metadata
    catalog=snapshot()
    models=WORKSPACE_MODELS
    if catalog:
        claims.pop('models');claims['catalog']=catalog[0];models=catalog[1]
    payload=base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    secret=os.environ['LAB_TOKEN_SECRET'].encode()
    if len(secret)<32: raise ValueError('LAB_TOKEN_SECRET must contain at least 32 bytes')
    token=payload+'.'+hmac.new(secret,payload.encode(),hashlib.sha256).hexdigest()
    return {'token':token,'model':MODEL,'models':models,'model_metadata':metadata() if catalog else [],'reasoning':REASONING,'expires':claims['exp']}
