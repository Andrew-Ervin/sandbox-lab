"""Authenticated operator views and explicit stop controls; no creation endpoints."""
import asyncio
from fastapi import HTTPException
from .azure_budget import RATES


def install(app):
    @app.get('/api/azure-runtime')
    async def status():
        from .azure_runtime import runtime, PROFILES
        from .runtime_provider import provider
        control = runtime()
        rows = []
        for kind in PROFILES:
            try:
                for ws in await control.list(kind):
                    record = control.record(ws['id'])
                    rows.append({'id':ws['id'],'name':ws['name'],'kind':kind,'status':ws['latest_build']['status'],'lease_until':record.get('lease_until',0),
                                 'startup_timings':record.get('startup_timings'), 'last_checkpoint_at':record.get('last_checkpoint_at'), 'storage_error':record.get('storage_error')})
            except Exception:
                for record in control.records(kind):
                    if record['state']!='deleted':rows.append({'id':record['id'],'name':record['name'],'kind':kind,'status':'unknown','lease_until':record.get('lease_until',0)})
        return {'provider':'azure','active_provider':provider(),'region':control.config.get('region','Not configured'),
                'storage_reviewed':bool(control.config.get('persistent_storage_reviewed')),'error':control.error or control.billing_error,
                'budget':{**control.budget.status(),'fixed_cost_approvals':control.config.get('fixed_cost_approvals',[])},'workspaces':rows,
                'storage':control.storage.status(),'storage_cost_review':control.config.get('storage_cost_review',{}),
                'warm':{kind:control.warm.status(kind) for kind in PROFILES},'max_hourly_compute_usd':control.config.get('max_hourly_compute_usd',12),'profiles':[{'kind':kind,**{k:control.profile(kind)[k] for k in ('group','cpu','memory','active_limit','retained_limit','idle_seconds','suspend_mode')},'hourly_usd':RATES[kind],'lease_seconds':control.profile(kind)['seconds']} for kind in PROFILES]}

    @app.post('/api/azure-runtime/stop')
    async def stop():
        from .azure_runtime import runtime
        from .previews import previews
        control = runtime(); control.warm.pause(); failed = []
        for record in control.records():
            if record['state'] in ('deleted','stopped'):continue
            try:
                await previews.remove_workspace(record['id'])
                await control.stop(record['id'],delete=record.get('disposable',False))
            except Exception: failed.append(record['id'])
        if failed:raise HTTPException(503,'Some Azure stops are unconfirmed. Reservations and workspace records are retained.')
        return {'stopped':True,'budget':control.budget.status()}
    return status
