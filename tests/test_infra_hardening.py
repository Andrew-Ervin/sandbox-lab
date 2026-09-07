from pathlib import Path
import yaml

DOCS=list(yaml.safe_load_all(Path('infra/lab.yaml').read_text()))
def resource(kind,name,ns='lab-control'):
    return next(d for d in DOCS if d['kind']==kind and d['metadata']['name']==name and d['metadata'].get('namespace')==ns)

def test_gateways_cannot_bypass_egress_proxy():
    for name in ['model-gateway','package-proxy']:
        egress=resource('NetworkPolicy',name)['spec']['egress']
        assert not any('ipBlock' in peer for rule in egress for peer in rule.get('to',[]))
        assert any(peer.get('podSelector',{}).get('matchLabels',{}).get('app')==name+'-egress' for rule in egress for peer in rule.get('to',[]))
        config=resource('ConfigMap',name+'-egress')['data']['squid.conf']
        assert 'http_access deny all' in config
        assert 'http_access deny private_dst' in config
        assert 'dstdomain -n' in config

def test_databases_only_accept_matching_coder():
    for ns in ['coder','coder-ai']:
        policy=resource('NetworkPolicy','postgres',ns)['spec']
        assert policy['egress']==[]
        peers=policy['ingress'][0]['from']
        assert len(peers)==1
        assert peers[0]['namespaceSelector']['matchLabels']['kubernetes.io/metadata.name']==ns
        assert peers[0]['podSelector']['matchLabels']=={'app':'coder'}
        resource('NetworkPolicy','default-deny',ns)

def test_services_have_startup_and_liveness_probes():
    for d in DOCS:
        if d['kind']=='Deployment':
            for c in d['spec']['template']['spec']['containers']:
                assert all(k in c for k in ['startupProbe','livenessProbe','readinessProbe'])


def test_single_writer_rollouts_and_tolerant_probes():
    for name,ns in [('postgres','coder'),('postgres','coder-ai'),('package-proxy','lab-control')]:
        assert resource('Deployment',name,ns)['spec']['strategy']=={'type':'Recreate'}
    for d in DOCS:
        if d['kind']=='Deployment':
            for c in d['spec']['template']['spec']['containers']:
                for probe in ['readinessProbe','livenessProbe','startupProbe']:
                    assert c[probe]['timeoutSeconds']==5
                if c['name']=='postgres':
                    assert 'pg_isready' not in str(c['livenessProbe'])
