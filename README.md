# Sandbox Lab

A local workspace with tenant-bound Microsoft Entra sign-in and per-user history, projects and workstations for chat, Python, coding projects, generated apps and a browser editor. React, shadcn and ChatKit provide the interface; FastAPI owns jobs and inference. All remote execution uses **Azure Container Apps Sandboxes**. OpenRouter supplies the configured model.

## Run locally

Follow [local setup](docs/LOCAL-SETUP.md), provide your own private credentials, then run `.venv/bin/python scripts/start.py`. Open http://127.0.0.1:3000. This starts local services; resource provisioning is a separate explicit operation. The source and architecture report contain no user conversations or workspace data.

## Execution and ownership

| Work | Compute | Persistence |
|---|---|---|
| Ordinary conversation | Local broker and model inference | Local SQLite history; no project allocation |
| Short Python | Custom scientific image, 1 CPU / 2 GiB | Per-chat files and artifacts; fresh interpreter each call |
| Headless coding | One sandbox per project, 2 CPU / 4 GiB | Independent project home; chats in that project reuse it |
| Developer workstation | Independent sandbox, 1 CPU / 2 GiB by default; selectable through 4 CPU / 8 GiB | VS Code, Pi/Ori and developer packages/history |
| App | Process in the owning project's or workstation's sandbox | Saved source and launch recipe; no separate Azure app per preview |

Source synchronizes between linked headless and developer homes on handoff and every 15 seconds while both are active. Three-way comparison preserves conflicting changes for a user choice. Credentials, dependencies, unsaved buffers and processes stay separate. See [projects](docs/PROJECTS.md).

The runtime keeps one clean spare per recently used role, then releases it after ten minutes without demand. Workspaces suspend after ten idle minutes. Current high-concurrency quotas are guarded by a cumulative $200 testing budget and a $12/hour aggregate compute allowance. This local process is not a production multi-tenant scheduler. See [scaling](docs/SCALING.md) and [Azure runtime](docs/AZURE-SANDBOX-RUNTIME.md).

Project names use 1–4 words from the opening request. Workstations receive a reviewable suggestion after first exit. Thread titles aim for 1–5 words. Opening, renaming or reading a conversation does not promote it in history; new messages do.

## Controls and validation

Quick code has no network or model credential. Headless inference stays in the trusted broker. Developer tools share a short-lived capability for that workstation's OpenRouter gateway; developer code can reuse that capability. Package downloads retain the five-day age gate and explicit human exceptions. See [security](docs/SECURITY.md), [packages](docs/PACKAGES.md), and [GUI tools](docs/GUI_HARNESSES.md).

Operations shows resource allocations, running/warm/queued counts, event durations, failures and estimated/reserved cost. Azure billing is delayed. Stop compute in Azure runtime to retain saved files and stop metered execution. Stored data and the approved Basic registry continue to incur their respective charges.

Validate changes with `.venv/bin/python -m pytest -q`, `npm run test:polling`, `npx tsc --noEmit`, and `npm run build`. Build the standalone [architecture field guide](reports/architecture/architecture.html) with `node scripts/build_embeds.mjs report`. See [validation](docs/VALIDATION.md).

Keep `.local`, `.env`, credentials, generated apps, conversation records and workspace files private. Run `python3 scripts/repo_audit.py --staged` on the exact index before any commit. Public publication requires explicit user authorization.

User identity and editor preferences are described in [Identity and personal settings](docs/IDENTITY.md). Workspace display names are independent of runtime identifiers. New workspaces default to 1 CPU / 2 GiB; the sandbox tiers are 1 / 2 / 20 GiB, 2 / 4 / 40 GiB and 4 / 8 / 80 GiB CPU, memory and disk. Changing size transfers the saved home to a new sandbox and reapplies the user's portable editor profile. The original stopped sandbox is retained for recovery.

For the ACA/AKS comparison and review-only network/identity templates, see [Network controls and workload identity](docs/NETWORK-IDENTITY.md).

[Workspace MCP examples](infra/azure-sandbox-pilot/examples/README.md) demonstrate
managed connector attachment, direct Microsoft Learn tools, and scoped GitHub PR
egress. See [Sandboxes versus regular Container Apps](docs/CONTAINER-APPS-CHOICE.md)
for the service choice and startup/cost tradeoffs.

See [execution profiling and retention economics](docs/PERFORMANCE-PROFILE.md) for measured fresh, concurrent and live execution latency. Python reuses an owner-scoped conversation sandbox while active, saves a checkpoint after each call, and deletes idle compute after ten minutes. Operations includes a read-only deployed-service inventory and package/storage usage.

See [sandbox storage and archival](docs/SANDBOX-STORAGE.md) for the opt-in seven-day home-to-Blob policy, verified rebuild, safety limits and startup measurements.

Built-in Python comparison, measured latency and billing: [Conversation Python and built-in sessions](docs/PYTHON-SESSION-COMPARISON.md).
