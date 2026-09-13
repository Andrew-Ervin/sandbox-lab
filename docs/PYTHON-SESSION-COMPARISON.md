# Conversation Python and built-in sessions

The default quick-Python path uses one preinstalled scientific sandbox per owner/conversation while it is live. Concurrent calls in one conversation serialize. Calls start fresh interpreters, preserve bounded working-file checkpoints locally and in private Blob, and do not carry model credentials. Ten idle minutes or the compute lease/budget boundary releases the disposable VM. The next request reconstructs from saved files. Explicit conversation/project deletion removes its matching quick VM and Blob checkpoint before removing local history.

`infra/azure-sandbox-pilot/builtin-sessions.json` creates a separate built-in PythonLTS pool for comparison: 10 concurrent sessions, 3,300 seconds of inactivity, blocked egress, no custom image, dedicated environment, registry or workload identity. `scripts/builtin_session_client.py` hashes owner plus conversation into a stable session ID; callers must authenticate and authorize the conversation before invoking it. This comparison client is not the default `run_python` backend. The pool keeps interpreter state and `/mnt/data` until expiry; it has no automatic durable-file restore. Never put provider keys or Azure credentials inside it.

The built-in network setting is all-or-nothing. Egress remains disabled; installing uv or packages from arbitrary internet endpoints is not enabled. The observed image includes Polars, NumPy, SciPy, Plotly and scikit-learn, but not uv. An attempted request to PyPI failed. The custom sandbox retains the existing minimum-package-age gateway for roles that permit package installation.

## Measured pilot results

A small standard-library example summed squares 0 through 9,999 and saved the verified result 333283335000. Times are local roundtrip samples, not service guarantees or percentiles at production load. Pool token acquisition and pool provisioning are outside execution timings. Pool runs save a file in its ephemeral filesystem; sandbox timings include durable checkpoint work, so these are distinct persistence contracts.

| Path | First / fresh runs | Follow-ups in one live environment |
|---|---|---|
| Built-in pool, supplied Python | 0.227 s first; five overlapping fresh sessions 0.148–0.351 s | Five calls 0.050–0.076 s; median 0.063 s |
| Chat model writes Python, conversation sandbox executes | Three runs 5.04–6.64 s | Three runs 3.59–4.59 s |
| Pi through Ori writes and executes | Three runs 17.71–19.90 s | Three runs 11.20–14.22 s |

Both model paths used the configured Luna model and its configured reasoning level. Direct Python has one code-generation call; Pi manages its tool loop inside a new disposable test workspace. Fresh Pi timing includes app-only workspace bootstrap and harness setup; follow-ups reuse that workspace but start a new Pi invocation. These are code-generation/execution comparisons, not full browser-to-final-chat-message timings. Pi has advantages for iterative repository editing; it did not improve this short numerical task.

The quick runtime portion alone was 2.07–4.10 s fresh and 0.762–0.786 s live in this test. All expected artifacts were verified. Test-owned sandbox compute was deleted afterwards. Built-in test sessions expire through the configured idle window.

## Allocation and cost

The built-in session reported a cgroup CPU quota of 100,000 microseconds per 100,000 microsecond period: **1 vCPU**, despite exposing four host CPUs to Python. Its cgroup memory limit was **4 GiB**. `/mnt/data` reported about **19.49 GiB total**, with about **13.83 GiB free** at observation. This filesystem observation is not a guaranteed session storage entitlement.

The East US 2 retail meter observed during this pilot is $0.03 per allocated built-in session-hour. Azure rounds allocated duration up to whole hours. A 55-minute idle window leaves five minutes of headroom for a one-hour bill, but repeated calls reset idle expiry and can cross additional billing hours. Empty built-in pool capacity does not require a dedicated node charge.

| Configuration | Active compute estimate | Short-use implication |
|---|---:|---|
| Built-in Python, 1 CPU / 4 GiB | $0.03 per rounded allocated hour | Usually $0.03 for a brief session with 55-minute expiry; 1,000 such sessions about $30 |
| Current quick sandbox, 1 CPU / 2 GiB | $0.108 per active hour | Ten idle minutes add $0.018 per one-time conversation, plus actual execution |
| Native sandbox tier with 4 GiB, 2 CPU | $0.216 per active hour | Twice the CPU of the built-in session; not an exact compute match |
| Arithmetic 1 CPU / 4 GiB at general consumption rates | $0.1296 per active hour | Price normalization only; not a selectable native sandbox tier |

At a full 55 active minutes, the current quick sandbox is about $0.099 versus $0.03 for a one-hour built-in allocation. At very short lifetimes, per-second sandbox billing can be cheaper; its ten-minute warm tail must be included. Blob, retained-state storage, requests and model inference are separate. The built-in comparison has a $1 reservation within the existing $200 pilot cap.

Sources: [session-pool configuration](https://learn.microsoft.com/en-us/azure/container-apps/session-pool), [code-interpreter APIs](https://learn.microsoft.com/en-us/azure/container-apps/sessions-code-interpreter), [hourly rounding](https://learn.microsoft.com/en-us/azure/container-apps/billing#code-interpreter), [Azure pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/).
