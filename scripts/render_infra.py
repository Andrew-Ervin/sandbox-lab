"""Render the lab's reproducible resources. Secrets are applied separately."""
from pathlib import Path
import yaml,os
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
native_agents=os.getenv('PROJECT_ENGINE','ori-pi')=='coder-native'
docs=[]
def add(kind,name,ns=None,**extra):
    api='v1'
    if kind in ('Deployment','StatefulSet'): api='apps/v1'
    if kind in ('Role','RoleBinding'): api='rbac.authorization.k8s.io/v1'
    if kind=='NetworkPolicy': api='networking.k8s.io/v1'
    obj={'apiVersion':api,'kind':kind,'metadata':{'name':name}}
    if ns: obj['metadata']['namespace']=ns
    obj.update(extra); docs.append(obj); return obj
for ns in ['lab-sandboxes','lab-agents','lab-dev','lab-control','coder','coder-ai']:
    add('Namespace',ns)['metadata']['labels']={'pod-security.kubernetes.io/enforce':'restricted','pod-security.kubernetes.io/enforce-version':'v1.35'}
for ns,quota in [('lab-sandboxes',{'pods':'10','requests.cpu':'4','limits.cpu':'10','requests.memory':'4Gi','limits.memory':'10Gi','requests.storage':'10Gi','persistentvolumeclaims':'4'}),('lab-agents',{'pods':'4','requests.cpu':'3','limits.cpu':'8','requests.memory':'3Gi','limits.memory':'16Gi','requests.storage':'10Gi'}),('lab-dev',{'pods':'3','requests.cpu':'2','limits.cpu':'6','requests.memory':'3Gi','limits.memory':'12Gi','requests.storage':'10Gi'})]:
    if ns=='lab-agents':
        quota.update({'pods':os.getenv('PROJECT_MAX_RUNNING','4'),'requests.storage':os.getenv('AI_STORAGE_QUOTA','100Gi'),'persistentvolumeclaims':os.getenv('AI_MAX_RETAINED_WORKSPACES','50')})
    add('ResourceQuota','capacity',ns,spec={'hard':quota})
    add('ServiceAccount','unprivileged',ns,automountServiceAccountToken=False)
    add('NetworkPolicy','default-deny',ns,spec={'podSelector':{},'policyTypes':['Ingress','Egress']})
add('ServiceAccount','broker','lab-sandboxes',automountServiceAccountToken=False)
add('Role','broker','lab-sandboxes',rules=[{'apiGroups':[''],'resources':['pods','persistentvolumeclaims'],'verbs':['get','list','watch','create','patch','delete']},{'apiGroups':[''],'resources':['pods/exec','pods/portforward'],'verbs':['create','get']}])
add('RoleBinding','broker','lab-sandboxes',roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'broker'},subjects=[{'kind':'ServiceAccount','name':'broker','namespace':'lab-sandboxes'}])
add('ServiceAccount','coder','coder')
add('Role','workspace-provisioner','lab-dev',rules=[{'apiGroups':[''],'resources':['pods','persistentvolumeclaims','services'],'verbs':['get','list','watch','create','update','patch','delete']}])
add('Role','workspace-provisioner','lab-agents',rules=[{'apiGroups':[''],'resources':['pods','persistentvolumeclaims','services'],'verbs':['get','list','watch','create','update','patch','delete']}])
add('RoleBinding','coder-provisioner','lab-agents',roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'workspace-provisioner'},subjects=[{'kind':'ServiceAccount','name':'coder','namespace':'coder-ai'}])
add('RoleBinding','coder-provisioner','lab-dev',roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'workspace-provisioner'},subjects=[{'kind':'ServiceAccount','name':'coder','namespace':'coder'}])
peer=lambda ns,labels: {'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':ns}},'podSelector':{'matchLabels':labels}}
dns={'to':[peer('kube-system',{'k8s-app':'kube-dns'})],'ports':[{'protocol':'UDP','port':53},{'protocol':'TCP','port':53}]}
for ns,selector in [('lab-sandboxes',{'lab/mode':'persistent'}),('lab-agents',{}),('lab-dev',{})]:
    egress=[{'to':[peer('lab-control',{'app':'sandbox-dns'})],'ports':[{'protocol':'UDP','port':1053},{'protocol':'TCP','port':1053}]},{'to':[peer('lab-control',{'app':'model-gateway'})],'ports':[{'protocol':'TCP','port':8080}]},{'to':[peer('lab-control',{'app':'package-proxy'})],'ports':[{'protocol':'TCP','port':3128}]}]
    if ns in ('lab-dev','lab-agents'): egress.append({'to':[peer('coder-ai' if ns=='lab-agents' else 'coder',{'app':'coder'})],'ports':[{'protocol':'TCP','port':7080}]})
    if native_agents and ns!='lab-dev':egress=[rule for rule in egress if not any(p.get('port')==8080 for p in rule.get('ports',[]))]
    add('NetworkPolicy','allowed-egress',ns,spec={'podSelector':{'matchLabels':selector},'policyTypes':['Egress'],'egress':egress})
private=['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','127.0.0.0/8','169.254.0.0/16','100.64.0.0/10','0.0.0.0/8','224.0.0.0/4','240.0.0.0/4']
for app,port in [('model-gateway',8080),('package-proxy',3128)]:
    add('NetworkPolicy',app,'lab-control',spec={'podSelector':{'matchLabels':{'app':app}},'policyTypes':['Ingress','Egress'],'ingress':[{'from':[peer('lab-sandboxes',{'lab/mode':'persistent'}),peer('lab-dev',{}),peer('lab-agents',{})],'ports':[{'protocol':'TCP','port':port}]}],'egress':[dns,{'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':private}}],'ports':[{'protocol':'TCP','port':443}]}]})
security={'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000,'fsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}}
if native_agents:
    gateway=next(d for d in docs if d['kind']=='NetworkPolicy' and d['metadata']['name']=='model-gateway')
    gateway['spec']['ingress'][0]['from']=[peer('lab-dev',{})]
container_security={'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']},'readOnlyRootFilesystem':True}
def deploy(name,ns,image,port=None,**container_extra):
    container={'name':name,'image':image,'securityContext':container_security,'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}},**container_extra}
    spec={'securityContext':dict(security),'automountServiceAccountToken':False,'containers':[container]}
    if port: container['ports']=[{'containerPort':port}]; add('Service',name,ns,spec={'selector':{'app':name},'ports':[{'port':port,'targetPort':port}]})
    add('Deployment',name,ns,spec={'replicas':1,'selector':{'matchLabels':{'app':name}},'template':{'metadata':{'labels':{'app':name}},'spec':spec}})
    return spec,container
add('ConfigMap','gateway-code','lab-control',data={'gateway.py':(ROOT/'sandbox/gateway.py').read_text()})
s,c=deploy('model-gateway','lab-control','sandbox-lab/gateway:local',8080,command=['uvicorn','gateway:app','--app-dir','/app','--host','0.0.0.0','--port','8080','--no-access-log'],envFrom=[{'secretRef':{'name':'model-credentials'}}],volumeMounts=[{'name':'code','mountPath':'/app','readOnly':True}])
s['volumes']=[{'name':'code','configMap':{'name':'gateway-code'}}]
# Keep model gateway replacement predictable locally; no request ledger is used.
next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='model-gateway')['spec']['strategy']={'type':'Recreate'}
c['readinessProbe']={'httpGet':{'path':'/healthz','port':8080},'periodSeconds':3}
add('ConfigMap','package-code','lab-control',data={'package_gateway.py':(ROOT/'sandbox/package_gateway.py').read_text()})
add('ConfigMap','package-policy','lab-control',data={'packages.json':(ROOT/'infra/packages.json').read_text()})
add('PersistentVolumeClaim','package-cache','lab-control',spec={'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':'1Gi'}}})
s,c=deploy('package-proxy','lab-control','sandbox-lab/packages:local',3128,command=['uvicorn','package_gateway:app','--app-dir','/app','--host','0.0.0.0','--port','3128','--no-access-log'],volumeMounts=[{'name':'code','mountPath':'/app','readOnly':True},{'name':'policy','mountPath':'/policy','readOnly':True},{'name':'cache','mountPath':'/cache'}])
s['volumes']=[{'name':'code','configMap':{'name':'package-code'}},{'name':'policy','configMap':{'name':'package-policy'}},{'name':'cache','persistentVolumeClaim':{'claimName':'package-cache'}}]
c['resources']={'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}}
c['readinessProbe']={'httpGet':{'path':'/healthz','port':3128},'periodSeconds':3}
# Only cluster names resolve for coding pods. Arbitrary external DNS is refused.
core='''cluster.local:1053 {
  forward . 10.96.0.10
  cache 30
}
.:1053 {
  template IN ANY {
    rcode REFUSED
  }
}
'''
add('ConfigMap','sandbox-dns','lab-control',data={'Corefile':core})
s,c=deploy('sandbox-dns','lab-control','registry.k8s.io/coredns/coredns:v1.13.1',1053,command=['/coredns','-conf','/etc/coredns/Corefile'],volumeMounts=[{'name':'config','mountPath':'/etc/coredns','readOnly':True}])
# The official binary carries this file capability; it needs a matching bounding set.
c['securityContext']={**container_security,'capabilities':{'drop':['ALL'],'add':['NET_BIND_SERVICE']}}
s['volumes']=[{'name':'config','configMap':{'name':'sandbox-dns'}}]
svc=next(d for d in docs if d['kind']=='Service' and d['metadata']['name']=='sandbox-dns')
svc['spec'].update(clusterIP='10.96.0.53',ports=[{'name':'udp','port':53,'targetPort':1053,'protocol':'UDP'},{'name':'tcp','port':53,'targetPort':1053,'protocol':'TCP'}])
add('NetworkPolicy','sandbox-dns','lab-control',spec={'podSelector':{'matchLabels':{'app':'sandbox-dns'}},'policyTypes':['Ingress','Egress'],'ingress':[{'from':[peer('lab-dev',{}),peer('lab-agents',{})],'ports':[{'protocol':'UDP','port':1053},{'protocol':'TCP','port':1053}]}],'egress':[dns]})
add('PersistentVolumeClaim','postgres','coder',spec={'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':'1Gi'}}})
s,c=deploy('postgres','coder','postgres:16.10-bookworm',5432,env=[{'name':'POSTGRES_USER','value':'coder'},{'name':'POSTGRES_DB','value':'coder'},{'name':'POSTGRES_PASSWORD','valueFrom':{'secretKeyRef':{'name':'database','key':'password'}}},{'name':'PGDATA','value':'/data/pgdata'}],volumeMounts=[{'name':'data','mountPath':'/data'},{'name':'tmp','mountPath':'/tmp'},{'name':'run','mountPath':'/var/run/postgresql'}])
s['securityContext'].update(runAsUser=999,runAsGroup=999,fsGroup=999)
s['volumes']=[{'name':'data','persistentVolumeClaim':{'claimName':'postgres'}},{'name':'tmp','emptyDir':{}},{'name':'run','emptyDir':{}}]
s,c=deploy('coder','coder','ghcr.io/coder/coder:v2.36.4',7080,command=['/opt/coder','server'],env=[{'name':'CODER_PG_CONNECTION_URL','valueFrom':{'secretKeyRef':{'name':'database','key':'url'}}},{'name':'CODER_ACCESS_URL','value':'http://coder.coder.svc.cluster.local:7080'},{'name':'CODER_HTTP_ADDRESS','value':'0.0.0.0:7080'},{'name':'CODER_WILDCARD_ACCESS_URL','value':''},{'name':'CODER_TELEMETRY_ENABLE','value':'false'},{'name':'CODER_UPDATE_CHECK','value':'false'},{'name':'CODER_OAUTH2_GITHUB_DEFAULT_PROVIDER_ENABLE','value':'false'},{'name':'CODER_DERP_SERVER_STUN_ADDRESSES','value':'disable'},{'name':'CODER_DERP_FORCE_WEBSOCKETS','value':'true'}],volumeMounts=[{'name':'home','mountPath':'/home/coder'},{'name':'tmp','mountPath':'/tmp'}])
s.update(serviceAccountName='coder',automountServiceAccountToken=True)
s['securityContext']={'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000,'fsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}}
s['volumes']=[{'name':'home','emptyDir':{'sizeLimit':'2Gi'}},{'name':'tmp','emptyDir':{'sizeLimit':'1Gi'}}]
c['resources']={'requests':{'cpu':'250m','memory':'256Mi'},'limits':{'cpu':'2','memory':'1Gi'}}
c['readinessProbe']={'httpGet':{'path':'/healthz','port':7080},'periodSeconds':5}
# Independent AI Coder control plane and database; only headless templates are published here.
import copy
for obj in list(docs):
    if obj.get('metadata',{}).get('namespace')=='coder' and obj['kind'] in ['ServiceAccount','PersistentVolumeClaim','Service','Deployment']:
        clone=copy.deepcopy(obj); clone['metadata']['namespace']='coder-ai'
        if clone['kind']=='Deployment':
            for ctr in clone['spec']['template']['spec']['containers']:
                for entry in ctr.get('env',[]):
                    if entry.get('name')=='CODER_ACCESS_URL': entry['value']='http://coder.coder-ai.svc.cluster.local:7080'
        docs.append(clone)
# Trusted control planes: isolate databases and allow only explicit service paths.
for ns,workspace_ns in [('coder','lab-dev'),('coder-ai','lab-agents')]:
    add('NetworkPolicy','default-deny',ns,spec={'podSelector':{},'policyTypes':['Ingress','Egress']})
    add('NetworkPolicy','postgres',ns,spec={'podSelector':{'matchLabels':{'app':'postgres'}},'policyTypes':['Ingress','Egress'],'ingress':[{'from':[peer(ns,{'app':'coder'})],'ports':[{'protocol':'TCP','port':5432}]}],'egress':[]})
    add('NetworkPolicy','coder',ns,spec={'podSelector':{'matchLabels':{'app':'coder'}},'policyTypes':['Ingress','Egress'],'ingress':[{'from':[peer(workspace_ns,{})],'ports':[{'protocol':'TCP','port':7080}]}],'egress':[dns,{'to':[peer(ns,{'app':'postgres'})],'ports':[{'protocol':'TCP','port':5432}]},{'to':[{'ipBlock':{'cidr':os.getenv('KUBE_API_NETWORK','172.19.0.2/32')}}],'ports':[{'protocol':'TCP','port':6443}]},{'to':[{'ipBlock':{'cidr':'10.96.0.1/32'}}],'ports':[{'protocol':'TCP','port':443}]},{'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':private}}],'ports':[{'protocol':'TCP','port':443}]}]})
# Separate CONNECT proxies prevent either gateway from bypassing its destination list.
registry_hosts=['pypi.org','files.pythonhosted.org','registry.npmjs.org','index.crates.io','crates.io','static.crates.io','proxy.golang.org','api.nuget.org','sum.golang.org','us-east.pkg.julialang.org','storage.julialang.net']
for source,hosts in [('model-gateway',['openrouter.ai']),('package-proxy',registry_hosts)]:
    name=source+'-egress'
    config='\n'.join(['http_port 3129','pid_filename /tmp/squid.pid','access_log none','cache_log /dev/null','cache_store_log none','cache deny all','acl connect method CONNECT','acl tls port 443','acl approved dstdomain -n '+' '.join(hosts),'acl private_dst dst '+' '.join(private),'http_access deny private_dst','http_access allow connect tls approved','http_access deny all','shutdown_lifetime 1 seconds'])+'\n'
    add('ConfigMap',name,'lab-control',data={'squid.conf':config})
    ps,pc=deploy(name,'lab-control','sandbox-lab/egress:local',3129,command=['squid','-N','-f','/etc/squid/squid.conf'],volumeMounts=[{'name':'config','mountPath':'/etc/squid','readOnly':True},{'name':'tmp','mountPath':'/tmp'}])
    ps['volumes']=[{'name':'config','configMap':{'name':name}},{'name':'tmp','emptyDir':{'sizeLimit':'32Mi'}}]
    pc['readinessProbe']={'tcpSocket':{'port':3129},'periodSeconds':5}
    add('NetworkPolicy',name,'lab-control',spec={'podSelector':{'matchLabels':{'app':name}},'policyTypes':['Ingress','Egress'],'ingress':[{'from':[peer('lab-control',{'app':source})],'ports':[{'protocol':'TCP','port':3129}]}],'egress':[dns,{'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':private}}],'ports':[{'protocol':'TCP','port':443}]}]})
    policy=next(d for d in docs if d['kind']=='NetworkPolicy' and d['metadata']['name']==source)
    policy['spec']['egress']=[dns,{'to':[peer('lab-control',{'app':name})],'ports':[{'protocol':'TCP','port':3129}]}]
    deployment=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']==source)
    deployment['spec']['template']['spec']['containers'][0].setdefault('env',[]).append({'name':'UPSTREAM_PROXY','value':f'http://{name}.lab-control.svc.cluster.local:3129'})
# Startup grace prevents restart loops during boot; liveness checks stay local.
for d in docs:
    if d['kind']!='Deployment':continue
    if d['metadata']['name'] in ('postgres','package-proxy'):
        d['spec']['strategy']={'type':'Recreate'}
    for c in d['spec']['template']['spec']['containers']:
        if c['name']=='postgres':c['readinessProbe']={'exec':{'command':['pg_isready','-U','coder','-d','coder']},'periodSeconds':5}
        if c['name']=='sandbox-dns':
            docs_config=next(x for x in docs if x['kind']=='ConfigMap' and x['metadata']['name']=='sandbox-dns')
            docs_config['data']['Corefile']=docs_config['data']['Corefile'].replace('cluster.local:1053 {','cluster.local:1053 {\n  health :8080\n  ready :8181')
            c['readinessProbe']={'httpGet':{'path':'/ready','port':8181},'periodSeconds':5}
            c['livenessProbe']={'httpGet':{'path':'/health','port':8080},'periodSeconds':10,'failureThreshold':6}
        if 'readinessProbe' in c:
            c['readinessProbe']['timeoutSeconds']=5
            c['startupProbe']={**copy.deepcopy(c['readinessProbe']),'periodSeconds':5,'failureThreshold':36}
            c.setdefault('livenessProbe',{**copy.deepcopy(c['readinessProbe']),'periodSeconds':10,'failureThreshold':6})
            c['livenessProbe']['timeoutSeconds']=5
            if c['name']=='postgres':
                # A busy/recovering database must not be killed just for refusing connections.
                c['livenessProbe']={'exec':{'command':['sh','-c','kill -0 1']},'timeoutSeconds':5,'periodSeconds':10,'failureThreshold':6}

(ROOT/'infra/lab.yaml').write_text(yaml.safe_dump_all(docs,sort_keys=False))
