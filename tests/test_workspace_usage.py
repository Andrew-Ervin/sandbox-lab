from backend.workspace_usage import observe,suggestion

def test_requires_observed_history_and_never_suggests_upsize():
    u={}
    assert suggestion(u,'performance') is None
    for i in range(12):u=observe(u,{'memory_peak_bytes':500_000_000,'cpu_usage_usec':i*3_000_000},i*30)
    assert suggestion(u,'performance')=='light'
    assert suggestion(u,'light') is None
    u=observe(u,{'memory_peak_bytes':7*2**30,'cpu_usage_usec':40_000_000},400)
    assert suggestion(u,'performance') is None
