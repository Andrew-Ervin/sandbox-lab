"""Bounded, conversation-scoped inputs. Code never reads the host filesystem."""
import base64
from .config import STATE

def inputs(store, thread_id, names=None):
    available = store.files(thread_id)
    if names is not None:
        if not isinstance(names, list) or len(names)>40 or any(not isinstance(n,str) for n in names):
            raise ValueError('Choose at most 40 conversation files')
        available = [f for f in available if f['name'] in names]
        if set(names) != {f['name'] for f in available}: raise ValueError('Input file is not in this conversation')
    result=[]; size=0
    for f in available:
        path=STATE/'artifacts'/f['run_id']/f['name']
        if path.is_symlink() or not path.is_file(): continue
        if size+f['size']>16_000_000: raise ValueError('Inputs exceed 16 MB; select fewer files')
        raw=path.read_bytes()
        if len(raw)>8_000_000: continue
        size+=len(raw)
        result.append({'name':f['name'],'data':base64.b64encode(raw).decode()})
    return result
