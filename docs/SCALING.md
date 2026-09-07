# Local scaling and warm starts

Implemented 2026-09-06. Kubernetes runs on the local Linux Docker engine or Docker Desktop VM. This update optimizes allocation, reuse and idle cleanup. See [the AKS draft](AKS-DRAFT.md) for the production migration.

## Independent lifecycles

| Domain | Starts when | Reuse | Stops when |
|---|---|---|---|
| Quick Python | Computation arrives; Auto/Quick also prewarms while the model thinks | Clean unused pods only; every executed pod is destroyed | Unclaimed reserve drains after 300 seconds without activity; can reach zero |
| Headless project | Chat delegates to its configured Coder-backed engine | The project's home, packages and files; engine-specific conversation history | 5 minutes idle; an unused project may stop earlier under capacity pressure |
| Human workstation | User starts/opens Developer workspaces | Separate home, VS Code and Pi/Ori session | 10 minutes idle; editor/Pi activity extends the deadline |

Stopping compute preserves the project's PVC. Active jobs, provisioning workspaces and app previews are protected from capacity-pressure eviction. Idle cleanup protects active jobs and previews. Closing the browser does not cancel a chat run. Coder, PostgreSQL, Docker, the kind node and local servers remain available when execution is zero.

## Implemented optimizations

- Kubernetes watch events wake waiting quick executions as readiness changes. Periodic lists recover broken watches; the one-second acquisition polling delay is gone.
- Claims immediately trigger refill, overlapping replacement creation with execution. Resource-version checks make claiming and retirement conditional on a pod still being unclaimed.
- The reserve target uses recent arrivals and observed refill duration, bounded by configurable baseline/maximum values. Activity holds a reserve; idle time releases it. Used pods never reenter the pool.
- Separate limits bound execution concurrency, admitted jobs and total quick pods. Status displays queue depth, active/ready pods, reserve target, warm hits/misses and timings. Warm quick compute requests a temporary reserve.
- GUI workstations use Pi/Ori. Headless execution selects native Coder control-plane inference or the optional in-pod Ori/Pi engine. Native inference uses the same configured model/reasoning as the main chat. Project homes are shared by their conversations, with serialized project execution.
- The app and model gateway reuse HTTP connections. Infrastructure health checks share a short cache. UI polling slows when idle/hidden, and historical link migration runs once.
- Unused preview listeners and Coder forwards close after two minutes; visible previews renew their lease. Idle workspace cleanup preserves files and packages.
- Retained AI storage has a separate quota from active compute. Capacity pressure can stop an unused AI workspace before starting another; human workspaces are never selected by this mechanism.

## Defaults and limits

Override runtime values in `.env`, then restart the backend. Regenerate/apply `infra/lab.yaml` for quotas. Raising application concurrency alone does not raise CPU, memory or storage quotas.

| Setting | Default | Meaning |
|---|---:|---|
| `QUICK_CONCURRENCY` | 4 | Active quick executions |
| `QUICK_MAX_PODS` | 8 | Active plus unclaimed quick pods |
| `WARM_POOL_SIZE` / `WARM_POOL_MAX` | 2 / 4 | Baseline / maximum unclaimed reserve during activity |
| `QUICK_IDLE_SECONDS` | 300 | Reserve idle drain |
| `PROJECT_CONCURRENCY` | 2 | Headless coding turns |
| `PROJECT_MAX_RUNNING` | 4 | AI workspace pod budget and rendered namespace pod quota |
| `PROJECT_IDLE_SECONDS` | 300 | AI idle stop |
| `DEVELOPER_IDLE_SECONDS` | 600 | Human idle stop |
| `PREVIEW_IDLE_SECONDS` | 120 | Unrenewed listener/forward expiry |
| `JOB_CONCURRENCY` / `JOB_MAX_PENDING` | 8 / 64 | Concurrent chat jobs / total admitted jobs |
| `AI_STORAGE_QUOTA` / `AI_MAX_RETAINED_WORKSPACES` | 100Gi / 50 | Requested PVC storage / retained AI PVC count |

Local capacity depends on the Docker engine/VM allocation. These experiment limits allow overcommit; four memory-heavy projects plus four quick jobs are not guaranteed to fit. The kind local-path PVC request is not an enforced filesystem quota. Retained artifacts consume disk separately. No automatic file deletion was introduced.

## Live verification

The standalone smoke used a two-second idle timer, two execution slots and four total pods. It passed: zero → cold execution → six queued executions → zero → another execution → zero. All eight executions returned 42; live pods never exceeded four.

| Measurement | Observed |
|---|---:|
| First allocation from zero, cached image | 0.6582 s |
| Ready acquisition, first burst pair | 0.0110–0.0255 s |
| Replacement acquisition, subsequent pairs | 0.2212–0.4654 s |
| Second allocation from zero | 0.9546 s |
| Second cold execution, end to end | 1.0767 s |

Burst executions deliberately slept 0.4 seconds; excess work queued behind two slots. These are functional smoke measurements on a running node with cached images, not production percentiles or cold-node measurements. Model latency is excluded. Earlier polling measurements are a historical diagnostic, not a controlled speedup comparison.

Run `.venv/bin/python -m scripts.smoke_scaling` with the backend stopped so only one controller owns the quick namespace. Results: `.local/scaling-smoke.json`. With the app running, `.venv/bin/python -m scripts.smoke_pi` tests real ChatKit → Coder → Ori → Pi turns using the OpenRouter account. The live test confirmed file persistence, same-workspace reuse, executed tool traces and session recall (initial provision 12.254 s; warm reuse 0.0392 s, excluding model execution); results are in `.local/pi-handoff-smoke.json`.

Regression tests cover burst growth, readiness wake-up, safe retirement, pod ceilings, workspace protections and preview cleanup. The controller and job queue are still single-process. Distributed ownership, durable workers, forecasting and Azure node scaling are migration work.

The final Pi/Ori image also resumed the stopped test workspace with its files/session intact. `scripts/smoke_pi_app.py` built a Go HTTP server, verified it after the coding turn exited, and checked the isolated preview response and CSP. The embedded developer terminal returned `DEFAULT_AGENT_READY` with Luna/xhigh displayed and no sign-in wizard. Those early checks were historical smoke tests. See VALIDATION.md for the current regression and browser results.

## App open and idle

Opening Apps or a developer workstation uses lifecycle endpoints, not an AI prompt. An app resumes its home, replays `project/.lab/app.json`, and waits for port 3000. A per-workspace lock prevents duplicate launches. The UI renews every 30 seconds only with recent visible interaction; the forwarding lease expires after 120 seconds without renewal. AI workspace idle is 300 seconds and human idle is 600 seconds; active work, setup, previews and real editor/Pi activity extend those deadlines. Main chat merely being open does not pin every environment. Static HTML apps need no coding pod.

The package gateway's bounded public cache and persistent artifact catalog reduce repeated registry downloads across projects; installed environments remain per-home. Images bake toolchains and use uv for Python. Five-day package quarantine is independent of compute warming: warming a pod cannot bypass it. The local DNS gate and package policy are part of workspace readiness.


## Current lifecycle and security revision

Quick reserve: five idle minutes, unassigned to any conversation. Used pods are destroyed. Quick source, artifacts and bounded working-file snapshots persist locally; no cloud storage is configured. A multi-language Coder project is allocated on `delegate_project`, or when a project chat continues existing developer source in its separate headless home. AI projects stop after five idle minutes, human workstations after ten, subject to active work and recent visible interaction. Background connections and status polling do not count. Pi Chat defaults to the right secondary sidebar and uses Ori → Pi → the trusted OpenRouter gateway. There is no package-name whitelist; only exact, expiring age exceptions. Live pod snapshots refresh every five seconds. See [the updated field guide](ARCHITECTURE-GUIDE.md) for enforcement, data paths, local credential scope and production gaps.

The local broker also keeps at most one **clean unassigned Coder project reserve** during new-chat demand. Only explicit `delegate_project` claims it. Used project homes never return to the reserve. It counts against total workspace capacity, stops after five idle minutes, and retains its unused clean home. The reserve is exposed in Lab status; set `PROJECT_WARM_RESERVE=0` to disable or `PROJECT_RESERVE_IDLE_SECONDS` to tune. AKS should replace this single-broker ledger with durable atomic leases and a demand-sized controller.

### Persistent-session recovery

The model gateway has no message-count ceiling. Tool-rich Pi histories retain
all messages; the 2 MB HTTP request bound and provider context window still apply.
Workspace model credentials have an expiry, but no request-count allowance. Long tool loops do not exhaust a per-grant call counter. Runtime deadlines, request-size limits and compute concurrency bounds remain.

Retained homes and running compute are separate capacities. Local defaults allow
50 retained AI homes / 100 GiB requested storage, while running pod limits remain
unchanged. Stopping a workspace preserves its home and does not free that quota.
The local-path storage driver does not enforce per-directory byte quotas.

Allocation recovers a conversation's stable Coder workspace name after an
ambiguous creation timeout. Build failures report quota errors, and empty timeout
exceptions produce an actionable message. The local Coder forward supervisor
checks service health and reconnects after two failed checks, including when
kubectl remains alive with stalled streams.


## Final application pass

Status queries remove source, task bodies, output and execution traces in SQLite before decoding JSON. Full run details remain available on demand. Active/queued jobs sort ahead of completed jobs so older in-flight work cannot disappear behind recent history. Job progress writes occur only when persisted job fields change, not for every stream event. Status dependencies and preview teardown run concurrently where independent.

Left history and right preview panes open exclusively. A brief collapse keeps an IDE iframe mounted; after an extended collapse reopening resolves its endpoint again to wake sleeping compute. Collapsed/hidden previews do not renew activity leases. Project Open in VS Code uses an idempotent project lock, resumes an existing link and creates no headless workspace. Documentation questions also allocate no project. These are local optimizations, not distributed-worker or AKS autoscaling implementations.

Developer saved-home capacity is separate from running compute: the namespace allows 40 GiB in PVC requests and 20 retained homes by default (`DEVELOPER_STORAGE_QUOTA`, `DEVELOPER_MAX_RETAINED_WORKSPACES` when rendering infrastructure). The three-pod compute cap is unchanged. Stopping a workstation frees compute, not its PVC request. On kind these requests are not hard filesystem usage quotas; monitor actual disk space separately.

GUI pods have a 1 GiB `/tmp` volume and a 2 GiB ephemeral-storage limit to accommodate cold native-extension installation. Headless scratch limits remain 256 MiB / 512 MiB. VSIX installer files are removed even after a failed installation. Prebaking pinned extensions into the production image should further reduce this cold-start cost.

Operational limits, deployment steps and retention ceilings are cataloged in [LIMITS.md](LIMITS.md). Public runtime defaults live in `config/limits.env`; private environment overrides stay out of Git.
