"""Read-only, bounded ARM inventory. No keys, settings or connection strings."""
import json
import re
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor


def inventory(config, credential):
    subscription=config['subscription_id']; group=config['resource_group']
    if not re.fullmatch(r'[a-fA-F0-9-]{36}',subscription) or not re.fullmatch(r'[\w.()-]{1,90}',group):raise ValueError('Invalid resource scope')
    root=f'/subscriptions/{subscription}/resourceGroups/{quote(group)}'
    token=credential.get_token('https://management.azure.com/.default').token
    def get(path,version):
        request=Request('https://management.azure.com'+path+('?api-version='+version),headers={'Authorization':'Bearer '+token})
        with urlopen(request,timeout=15) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('Inventory exceeds limit')
            return json.loads(raw)
    resources=get(root+'/resources','2021-04-01')
    if resources.get('nextLink'):raise ValueError('Inventory exceeds one bounded page')
    def describe(r):
        kind=r['type'].lower();rid=r['id'];result={'name':r['name'],'type':r['type'],'region':r.get('location'),'sku':(r.get('sku') or {}).get('name'),'metrics':{},'errors':[]}
        versions={'microsoft.app/sessionpools':'2025-07-01','microsoft.app/sandboxgroups':'2026-02-01-preview','microsoft.storage/storageaccounts':'2023-05-01','microsoft.containerregistry/registries':'2023-07-01','microsoft.managedidentity/userassignedidentities':'2023-01-31'}
        if kind not in versions:return {**result,'status':'Unreviewed resource type'}
        try:
            detail=get(rid,versions[kind]);p=detail.get('properties',{});result['status']=p.get('provisioningState','Present')
            if kind=='microsoft.app/sessionpools':
                result['metrics']={'containerType':p.get('containerType'),'maxConcurrentSessions':p.get('scaleConfiguration',{}).get('maxConcurrentSessions'),
                    'cooldownSeconds':p.get('dynamicPoolConfiguration',{}).get('lifecycleConfiguration',{}).get('cooldownPeriodInSeconds'),
                    'network':p.get('sessionNetworkConfiguration',{}).get('status'),'billing':'Allocated session-hours, rounded up' if p.get('containerType')=='PythonLTS' else 'Dedicated compute and session-management charges'}
            elif kind=='microsoft.app/sandboxgroups':
                result['metrics']={k:p.get(k) for k in ('defaultCpu','defaultMemory','defaultDisk','defaultTimeoutSeconds','maxSandboxCount','enableDetailedMetrics')}
            elif kind=='microsoft.storage/storageaccounts':
                result['metrics']={k:p.get(k) for k in ('accessTier','allowBlobPublicAccess','minimumTlsVersion')}
                bp=get(rid+'/blobServices/default','2023-05-01').get('properties',{})
                result['metrics'].update(versioning=bp.get('isVersioningEnabled'),soft_delete_days=bp.get('deleteRetentionPolicy',{}).get('days'))
            elif kind=='microsoft.containerregistry/registries':
                result['metrics'].update(admin_enabled=p.get('adminUserEnabled'),anonymous_pull=p.get('anonymousPullEnabled'))
                usage=get(rid+'/listUsages','2023-07-01')
                result['metrics']['usage']=[{k:u.get(k) for k in ('name','currentValue','limit','unit')} for u in usage.get('value',[])]
            elif kind=='microsoft.managedidentity/userassignedidentities':result['metrics']['credential_type']='Managed identity; no runtime compute'
        except HTTPError as e:result['errors'].append(f'Azure observation HTTP {e.code}')
        except Exception as e:result['errors'].append(type(e).__name__)
        return result
    with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(describe,resources.get('value',[])[:50]))
    return {'observed_at':time.time(),'services':rows}
