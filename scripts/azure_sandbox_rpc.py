"""One bounded SDK operation over private stdio. Never run workspace code locally."""
import base64
import dataclasses
import json
import sys
import contextlib

_clients = {}
_credential = None
_blob_clients = {}


def blob_invoke(config, action, args):
    from azure.storage.blob import BlobServiceClient, ContentSettings
    from azure.core import MatchConditions
    import re
    account = config['storage_account']
    if not re.fullmatch('[a-z0-9]{3,24}', account): raise ValueError('Invalid storage account')
    key = args['key']
    if not re.fullmatch(r'(workspaces|chats)/[a-f0-9-]{32,64}/latest.json',key): raise ValueError('Invalid checkpoint key')
    if account not in _blob_clients:
        _blob_clients[account] = BlobServiceClient('https://'+account+'.blob.core.windows.net', _credential, retry_total=0)
    blob = _blob_clients[account].get_blob_client('workspace-state', key)
    if action == 'blob_get':
        info = blob.get_blob_properties()
        if info.size > 70_000_000: raise ValueError('Checkpoint exceeds limit')
        raw = blob.download_blob(etag=info.etag, match_condition=MatchConditions.IfNotModified).readall()
        if len(raw) > 70_000_000: raise ValueError('Checkpoint exceeds limit')
        return {'data':base64.b64encode(raw).decode(), 'etag':info.etag}
    if action == 'blob_put':
        raw = base64.b64decode(args['data'], validate=True)
        if len(raw) > 70_000_000: raise ValueError('Checkpoint exceeds limit')
        # An absent expected ETag means CREATE, never unconditional overwrite.
        options = {'overwrite':False}
        if args.get('etag'): options = {'overwrite':True, 'etag':args['etag'], 'match_condition':MatchConditions.IfNotModified}
        result = blob.upload_blob(raw, content_settings=ContentSettings(content_type='application/json'), **options)
        return {'etag':result['etag'], 'bytes':len(raw)}
    raise ValueError('Unsupported Blob operation')


def client(config, group):
    """Reuse HTTP connections and the Entra token only inside the private worker."""
    global _credential
    from azure.identity import AzureCliCredential
    from azure.containerapps.sandbox import SandboxGroupClient, endpoint_for_region
    if _credential is None:
        from azure.core.credentials import AccessToken
        import time
        class CachedCliCredential:
            def __init__(self): self.cli = AzureCliCredential(); self.tokens = {}
            def get_token(self, *scopes, **kwargs):
                key = (scopes, kwargs.get('tenant_id'))
                token = self.tokens.get(key)
                if token is None or token.expires_on < time.time()+120:
                    token = self.cli.get_token(*scopes, **kwargs); self.tokens[key] = token
                return token
        _credential = CachedCliCredential()
    key = (config['subscription_id'], config['resource_group'], config['region'], group)
    if key not in _clients:
        _clients[key] = SandboxGroupClient(endpoint_for_region(config['region']), _credential,
            subscription_id=config['subscription_id'], resource_group=config['resource_group'],
            sandbox_group=group, retry_total=0, connection_timeout=15, read_timeout=45)
    return _clients[key]


def invoke(data):
    from azure.containerapps.sandbox import EgressPolicy
    config = data['config']
    with contextlib.nullcontext(client(config, data['group'])) as group:
        action = data['action']
        args = data.get('args', {})
        if action.startswith('blob_'): return blob_invoke(config, action, args)
        if action == 'delete_snapshot':group.begin_delete_snapshot(args['snapshot_id'],polling_timeout=90).result();return {}
        if action == 'list':
            return [dataclasses.asdict(s) for s in group.list_sandboxes()]
        if action == 'create':
            # No implicit Allow default, public app ports, registry imports, or volumes.
            sb = group.begin_create_sandbox(**args, egress_policy=EgressPolicy(default_action='Deny', traffic_inspection='Full'),
                                            polling_timeout=180).result()
            return dataclasses.asdict(sb.get())
        sb = group.get_sandbox_client(data['sandbox_id'])
        if action == 'get': return dataclasses.asdict(sb.get())
        if action == 'snapshot': return dataclasses.asdict(sb.begin_create_snapshot(polling_timeout=180).result())
        if action == 'exec': return dataclasses.asdict(sb.exec(args['command']))
        if action == 'write':
            sb.write_file(args['path'], base64.b64decode(args['data'], validate=True), mode=args.get('mode', '0600'))
            return {}
        if action == 'read':
            info = sb.stat_file(args['path'])
            size = getattr(info, 'size', None)
            if size is None or size > args['maximum']: raise ValueError('Remote file exceeds transfer limit')
            raw = sb.read_file(args['path'])
            if len(raw) > args['maximum']: raise ValueError('Remote file exceeds transfer limit')
            return {'data': base64.b64encode(raw).decode()}
        if action == 'remove_file': sb.delete_file(args['path']); return {}
        if action == 'stop': sb.begin_stop(polling_timeout=90).result(); return {}
        if action == 'resume': sb.begin_resume(polling_timeout=180).result(); return dataclasses.asdict(sb.get())
        if action == 'delete': sb.begin_delete(polling_timeout=90).result(); return {}
        if action == 'bridge_port':
            # This sole port terminates our authenticated root-owned relay. It is
            # never the generated app or IDE port. Auth is tested before use.
            existing=next((port for port in sb.get().ports if port.port==18443),None)
            return dataclasses.asdict(existing or sb.add_port(18443, anonymous=True))
        raise ValueError('Unsupported Azure operation')


if __name__ == '__main__':
    import struct
    if '--stream' in sys.argv:
        def exact(length):
            chunks = bytearray()
            while len(chunks) < length:
                part = sys.stdin.buffer.read(length-len(chunks))
                if not part: raise EOFError()
                chunks.extend(part)
            return chunks
        while True:
            try:
                length = struct.unpack('!I', exact(4))[0]
                if length > 180_000_000: raise ValueError('Request exceeds transfer limit')
                request = json.loads(exact(length))
            except EOFError: break
            try: result = {'result': invoke(request)}
            except Exception as error:
                result = {'error': type(error).__name__, 'status_code': getattr(error, 'status_code', None)}
            raw = json.dumps(result).encode()
            sys.stdout.buffer.write(struct.pack('!I', len(raw))+raw); sys.stdout.buffer.flush()
    else:
        try:
            request = json.loads(sys.stdin.buffer.read(180_000_000))
            print(json.dumps({'result': invoke(request)}))
        except Exception as error:
            print(json.dumps({'error': type(error).__name__, 'status_code': getattr(error, 'status_code', None)}))
            sys.exit(1)
