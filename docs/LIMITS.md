# Operational limits

Edit **`config/limits.env`** for public defaults. Process environment wins, then private `.env`, then this file. The backend validates the numeric values at startup. Do not put credentials in this file. No per-user message count is imposed on workspace model access.

| Setting group | Default | Takes effect |
| --- | --- | --- |
| `QUICK_CONCURRENCY`, `QUICK_MAX_PODS` | 4 executions, 8 total pods | Backend restart; new pods |
| `WARM_POOL_SIZE`, `WARM_POOL_MAX`, `QUICK_IDLE_SECONDS` | 2–4 spare pods while active; zero after 300 seconds idle | Backend restart |
| `PROJECT_CONCURRENCY`, `PROJECT_MAX_RUNNING` | 2 active project runs, 4 running headless homes | Backend restart; render/apply quota for running maximum |
| `PROJECT_WARM_RESERVE`, `PROJECT_RESERVE_IDLE_SECONDS` | 1 unassigned home while active; zero after 300 seconds | Backend restart |
| `PROJECT_IDLE_SECONDS`, `DEVELOPER_IDLE_SECONDS`, `PREVIEW_IDLE_SECONDS` | 300 / 600 / 120 seconds | Backend restart; new Coder workspace TTLs; preview heartbeat protects active use |
| `JOB_CONCURRENCY`, `JOB_MAX_PENDING` | 8 workers, 64 admitted jobs | Backend restart; one run at a time per conversation/project |
| `AI_STORAGE_QUOTA`, `AI_MAX_RETAINED_WORKSPACES` | 100 GiB requested, 50 homes | Render/apply cluster quota |
| `DEVELOPER_STORAGE_QUOTA`, `DEVELOPER_MAX_RETAINED_WORKSPACES`, `DEVELOPER_MAX_RUNNING` | 40 GiB requested, 20 homes, 3 pods | Render/apply cluster quota |
| `SYNC_MAX_FILES`, `SYNC_MAX_FILE_BYTES`, `SYNC_MAX_TOTAL_BYTES`, `SYNC_MAX_ENTRIES` | 2,000 files, 8 MB/file, 32 MB total, 10,000 scanned entries | Backend restart; limits are sent with trusted source-transfer helpers |
| `SYNC_CONCURRENCY`, `PROJECT_SYNC_SECONDS` | 2 transfers, 15 seconds between active-pair checks | Backend restart; sleeping workspaces are not awakened |
| `SYNC_MAX_IMPORTS` | 3 legacy import folders | Legacy import helper only; ongoing sync creates no snapshots |
| `BROKER_TOKEN_SECONDS`, `BROKER_RENEW_BEFORE_SECONDS` | 86,400-second token, renew 3,600 seconds before expiry | Local launcher watcher; only the scoped quick broker credential |
| `WEB_SEARCH_MAX_RESULTS`, `WEB_SEARCH_MAX_TOTAL_RESULTS`, `WEB_SEARCH_MAX_USES` | 3 results/search, 6 total, 2 searches/model request | Backend restart; render/apply/restart model gateway |
| `ARTIFACT_MAX_FILES`, `ARTIFACT_MAX_FILE_BYTES`, `ARTIFACT_MAX_TOTAL_BYTES` | 40 files, 8 MB/file, 16 MB total per collection/checkpoint | Backend restart; new quick pods; trusted headless collection helpers |
| `QUICK_CODE_CHARS`, `QUICK_CPU_SECONDS`, `QUICK_RUN_SECONDS`, `QUICK_STDOUT_BYTES` | 100,000 characters, 25 CPU seconds, 30 wall seconds, 64 KB output | Backend restart; new quick pods |
| `DICTATION_MAX_SECONDS`, `DICTATION_MAX_BYTES` | 300 seconds, 10 MB raw WAV | Rebuild/package Pi Chat; reinstall/reload extension; render/apply/restart gateway |
| `MODEL_MAX_BODY_BYTES` | 2 MB JSON per model request | Render/apply/restart gateway |

Bytes above are decimal. Upload JSON uses a derived base64 allowance. Dictation requires at least `(seconds + 2) × 32,000 + 44` bytes for mono PCM16 at 16 kHz; the tolerance covers recorder scheduling. Audio stays in memory and transcripts enter the draft without sending a chat message. Runtime limits do not grant credentials or broaden egress.

## Applying changes

1. Edit `config/limits.env`, or override selected keys in private `.env`. Run `.venv/bin/python -c "from backend.limits import validate; validate()"`.
2. Restart `scripts/start.py`. Existing quick pods retain their creation-time environment until consumed/expired; all newly created pods receive the new limits.
3. For cluster quota or gateway changes, run `.venv/bin/python scripts/render_infra.py`, inspect the generated manifest, and apply the relevant resources using the operator kubeconfig. Keep `PROJECT_ENGINE` consistent with the deployed engine; native Coder and Ori/Pi have different network policies. Restart the gateway after changing its ConfigMap.
4. For dictation changes, run `.venv/bin/python scripts/patch_pi_dictation.py` then `.venv/bin/python scripts/package_pi_chat.py`. Rebuild the developer image for future workstations, or run `scripts/configure_developer.py --workspace NAME` for an existing running workstation; reload VS Code. This patch replaces its previous version rather than appending duplicates.
5. Changing helper **code**, as opposed to the settings, requires rebuilding `sandbox/Dockerfile`'s quick target and loading/publishing that image. Source-transfer helpers are sent at call time.

On Windows, use Ubuntu/WSL2; `.venv/bin/python` and the local launcher are Linux paths. See `LOCAL-SETUP.md` for the supported setup.

## Infrastructure resource settings

These existing Kubernetes/Terraform fields are intentionally separate from application admission settings. Increase the appropriate aggregate quota as well as per-pod requests; changing one does not expand the other.

| Resource | Default and configuration location |
| --- | --- |
| Quick pod | `backend/compute.py:pod_manifest`: 100m CPU/128 MiB requested; 1 CPU/768 MiB/256 MiB ephemeral limits; 128 MiB work, 64 MiB memory tmp, 16 MiB home. Absolute pod deadline 30 minutes. |
| Coder homes | `infra/coder/main.tf`: 2 GiB PVC per home; template variables `cpu_request=500m`, `memory_request=512Mi`, `memory_limit=4Gi`; 2 CPU limit. Storage class is a template variable. |
| Coder scratch | Same template: GUI tmp 1 GiB/ephemeral 2 GiB; headless tmp 256 MiB/ephemeral 512 MiB; work scratch 256 MiB. |
| Namespace CPU/memory | `scripts/render_infra.py` quota table: quick requests 4 CPU/4 GiB, limits 10 CPU/10 GiB; headless requests 3 CPU/3 GiB, limits 8 CPU/16 GiB; GUI requests 2 CPU/3 GiB, limits 6 CPU/12 GiB. Quick namespace hard pod ceiling 10 and legacy PVC ceiling 4/10 GiB. |
| Package gateway | `infra/packages.json`: 5-day minimum release age, version-specific time-limited overrides; max artifact 250 MB. `sandbox/package_gateway.py`: metadata fetch bounds 16 MB (npm 64 MB); see `PACKAGES.md`. Cache PVC 1 GiB in `scripts/render_infra.py`. |
| Local Kubernetes VM | Docker Desktop/engine CPU, RAM and disk allocation are an outer ceiling. kind local-path PVC requested size is **not an enforced disk quota**. AKS needs a provisioner that enforces storage sizes and a resize policy. |

## Safety and presentation ceilings

These are code-level safeguards rather than scaling knobs. Keep them when increasing capacity: source paths at most 1,024 characters/16 segments; quick checkpoint paths 400 characters/8 segments; 1,024 open files per quick process; at most three Plotly renders per quick run and 14 seconds per renderer; inline plot specification 8 MB. Source exports exclude credential filenames, hidden dependency folders, symlinks and recursive imports. These exclusions are not content DLP.

`backend/file_view.py` bounds text previews to 200 KB/3,000 lines. `backend/approval_view.py` caps approval JSON at 1 MB and inline image payloads at 512 KB. `backend/documentation.py` reads at most 160 KB per curated document and returns at most 20 KB. Chat context uses the latest 30 saved items, with 24,000 characters per message; a response can make four orchestration rounds and two tools per round. Main model output defaults to 4,096 tokens; workspace gateway output is capped at 16,000. These bounds protect memory/context; full originals remain subject to the stored-file limits above. Change the named source files deliberately if a use case requires more.

## Retention and cleanup

Idle shutdown stops compute; it does **not** delete saved projects or their homes. Quick checkpoints retain only their latest snapshot; the mock OneDrive mirror retains only its latest successful copy. Ongoing source sync retains one hash baseline and updates working files; it does not create repeated snapshots. Legacy import folders remain until explicitly removed. Conversation artifacts retain historical versions until the owning conversation/project is deleted. There is no global disk budget or automatic age-based deletion of those historical files in this local prototype. Add production retention, storage accounting, user quotas and scheduled cleanup before serving thousands of users. See `AZURE-IMPLEMENTATION.md`.

Deletion has two background workers, up to eight attempts with at most 60 seconds retry delay, and seven days of completion tombstones (`backend/project_deletions.py`). Deleting a project does not implicitly delete an independently owned GUI workstation; delete that workstation explicitly as well.

The general assistant uses `CHAT_MAX_OUTPUT_TOKENS=4096` and `CHAT_PROVIDER_ATTEMPTS=3`; transient upstream 429/502/503/504 responses get short, bounded retries before any tool is executed. This does not add a message-count allowance. Ori/Pi headless turns use `ORI_RUN_SECONDS=600` (broker transport allows 30 extra seconds), and native Coder uses `NATIVE_RUN_SECONDS=900`. Workspace model gateway output still has its independent 16,000-token ceiling. A provider's own account/model rate limit can reject requests even with available local compute.

Message JSON is capped at 128 KB (`backend/main.py`). ChatKit acknowledges a queued user message before waiting for a worker. Rejoining a running conversation returns ChatKit's native locked status until completion, while other conversations can run independently. Idle chat views no longer reload their transcript every four seconds.

The local launcher renews the restricted quick-Python Kubernetes token before expiry, checks every 30 seconds, and atomically replaces its 0600 kubeconfig. Operator credentials remain in the host launcher. Production should use projected, rotating service-account credentials in the trusted broker; execution pods still receive no Kubernetes token.

Workspace model capabilities retain a hard one-hour lifetime. `WORKSPACE_TOKEN_RENEW_BEFORE_SECONDS=300` starts renewal five minutes before expiry for running, recently used GUI workspaces. The worker checks every 30 seconds, never wakes a sleeping workstation and does not renew its activity lease. Failed renewal preserves the existing token and retries. Pi's configured provider resolves its token-file command per request; dictation reads it per recording. Other native harnesses can cache credentials and may need a fresh terminal/session.

Native Coder activity refreshes at `NATIVE_TELEMETRY_SECONDS=5`, limited to the most recent `NATIVE_TELEMETRY_MAX_MESSAGES=200` messages and `NATIVE_TELEMETRY_MAX_CHARS=24000` rendered characters. Older activity can be omitted from this view. Reported usage covers retained messages and only fields provided by Coder; it is not an invoice or complete tenant billing ledger. Full activity is excluded from status/gallery polling payloads.

`NATIVE_STATUS_SECONDS=5` controls independent Coder status observation. The browser pauses its observer when hidden; the server continues tracking active or unconfirmed turns, with up to four concurrent reads. Idle sessions are read on demand rather than continuously polling all retained history. Status reads never renew workspace activity. Stop coding also stops headless compute, because native interrupt alone can leave shell children alive; saved files remain and previews reopen on demand. `CODER_READ_ATTEMPTS=3` retries read-only Coder requests; mutation requests are never automatically replayed on an ambiguous network failure. The main model request can retry a transport failure before dispatching local tools; duplicate inference/search cost is possible, but already completed execution and approved tools are not replayed. Artifact collection retries once before reporting that saved files remain available through Workspace files.

`APP_PACKAGE_RESTORE_SECONDS=120` bounds automatic npm dependency restoration for a copied app. The launcher allows that interval plus its existing two-minute listen deadline and 20-second connection allowance. Successful unchanged lockfiles skip reinstall; no release-age/network policy is bypassed.
