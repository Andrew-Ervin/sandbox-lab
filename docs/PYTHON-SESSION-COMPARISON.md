# Conversation Python and built-in sessions

The deployed routing uses a built-in Python session pool for quick numerical work, headless project sandboxes for unavailable dependencies, shell tools, repository changes or longer execution, and separate developer workspaces for interactive work. Ordinary discussion allocates none of these.

Set `builtin_session_endpoint` and `builtin_session_limit` in the private runtime configuration to select the pool. Without an endpoint, the custom scientific sandbox remains the explicit compatibility fallback. No uncertain execution is automatically replayed in another backend. The assistant is told the actual baseline instead of assuming all custom-image packages are present.

The pool has a 3,300-second inactivity timeout and a stable owner/conversation identity. Calls in one conversation serialize. Each call runs a fresh bounded interpreter; Python globals do not persist. Working files and artifacts follow the existing per-conversation checkpoint contract (40 files, 8 MB each, 16 MB total), with broker-owned local/Blob persistence. Payload and result files use Azure's file API to avoid inline-code/stdout truncation. Temporary program directories are separate from checkpointed working files. Azure credentials remain in the private credential worker.

The current pilot permits ten allocated pool sessions. New conversations beyond that limit fail before execution with a capacity explanation; this is a pilot guard, not a production queue. Continued activity can cross billing hours. A persistent local ledger conservatively accounts for allocated hours; it is not an Azure invoice. Operations distinguishes estimates/reservations, delayed provider billing and optional operator-reported spend. Session counts are broker estimates and do not include external clients. Deleting a conversation terminates its matching pool session before deleting saved state. Idle expiry needs no running broker.

Egress remains disabled. Polars, NumPy, SciPy, Plotly and scikit-learn were verified; uv is absent and a PyPI request failed. Missing dependencies belong in the headless environment with its existing five-day package-age gateway. Interactive Plotly HTML is retained; static rendering depends on tools in the built-in image.

The source template creates no dedicated environment, registry or workload identity. `scripts/builtin_session_client.py` remains a minimal comparison client; `backend/builtin_python.py` is the app adapter.

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

## App integration follow-up

The app adapter’s test artifact/save/restore calls took approximately 0.7–1.7 seconds including file transfer and checkpoint handling. Explicitly deleting a test session and recreating it restored its saved file successfully. These include work omitted by the bare execution comparison above. See [headless CLI comparison](HEADLESS-HARNESS-COMPARISON.md) for Pi, Codex and Claude Code on a larger coding task.
