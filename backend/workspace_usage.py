"""Conservative, advisory-only downsizing from observed guest usage."""
import math

def observe(previous, sample, now):
    result=dict(previous or {})
    memory=sample.get('memory_peak_bytes');cpu=sample.get('cpu_usage_usec')
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in (memory,cpu)):return result
    result['peak_memory_bytes']=max(result.get('peak_memory_bytes',0),memory)
    if now>result.get('last_at',now) and cpu>=result.get('last_cpu',cpu):
        used=(cpu-result['last_cpu'])/1e6/(now-result['last_at'])
        result['peak_sampled_cpu']=max(result.get('peak_sampled_cpu',0),used)
    result.setdefault('first_at',now)
    result.update(last_at=now,last_cpu=cpu,samples=result.get('samples',0)+1)
    return result

def suggestion(usage,current):
    if usage.get('samples',0)<10 or usage.get('last_at',0)-usage.get('first_at',0)<300:return None
    tiers=[('light',1,2),('balanced',2,4),('performance',4,8)]
    current_cpu=next((cpu for name,cpu,_ in tiers if name==current),4)
    for name,cpu,ram in tiers:
        if cpu>=current_cpu:return None
        if usage.get('peak_sampled_cpu',current_cpu)*1.5<cpu and usage.get('peak_memory_bytes',ram*2**30)*1.5<ram*2**30:
            return name
    return None
