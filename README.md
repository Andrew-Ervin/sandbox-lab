# Sandbox Lab

A local prototype for a general chat assistant that hands coding work to isolated Kubernetes environments. React, shadcn and ChatKit provide the UI; FastAPI owns chat jobs, project files, previews and lifecycle. OpenRouter supplies inference. Coder manages persistent headless and developer workspaces in separate control planes.

This is a **single-owner local lab**, not a production multi-tenant service. Windows uses Ubuntu/WSL2; Linux and macOS are supported bootstrap targets. Full clean-machine Windows/Linux validation remains outstanding.

## Start here

Follow [local setup](docs/LOCAL-SETUP.md) for prerequisites, pinned downloads, image builds and Coder bootstrap. Supply your own credentials in ignored `.env`. Never copy someone else's `.local` state or workspace volumes.

```sh
cp .env.example .env
# Privately configure credentials as described in LOCAL-SETUP.md.
bash scripts/download_tools.sh
bash scripts/setup.sh
# Complete the Coder bootstrap steps in LOCAL-SETUP.md, then:
.venv/bin/python scripts/start.py
```

Open `http://127.0.0.1:3000`. The launcher also maintains local Coder connections. Ports are loopback-only. Setup does not create a GitHub repository or publish anything.

## Execution choices

| Environment | Created when | Files and packages | Idle behavior |
|---|---|---|---|
| Ordinary chat | A user sends a message | Conversation only; no assigned code workspace | Server job survives browser navigation |
| Quick Python | The assistant requests computation | Prebuilt scientific image; bounded per-conversation checkpoints and artifacts | Single-use pod destroyed after each execution; unused reserve drains after five minutes |
| Headless project | The assistant explicitly delegates persistent/multi-language work | Project home PVC shared by chats in that project; language lockfiles and environments | Five idle minutes; stop preserves files |
| Developer workstation | User opens/creates a linked workstation | Independent home with VS Code, terminal, Pi/Ori and app previews | Ten idle minutes; stop preserves files |
| App preview | User opens an app | Process in its owning workspace; static artifacts need no workspace | Preview leases expire independently; reopening wakes compute without a chat message |

Open in VS Code and project-chat entry automatically synchronize source between separate workstations. Saved changes continue to sync every 15 seconds while both run; conflicting edits are kept for a user choice. Credentials, installed dependencies and processes stay separate. See [projects and sync](docs/PROJECTS.md).

The source default is `PROJECT_ENGINE=ori-pi`: Pi runs through Ori inside a headless Coder workspace. The **optional native Coder Agents engine**, used in the current local trial, runs inference in Coder's control plane and keeps model credentials/routes out of headless code. Configure it using [the native engine guide](docs/NATIVE_CODER_TRIAL.md). GUI workstations remain Pi/Ori independently of that choice.

Quick Python uses uv-built image dependencies; it has no package-download network. Missing packages move the task to a project, where uv, npm, NuGet, Julia Pkg, Go modules and Cargo manage the appropriate environment. Packages are not name-whitelisted: downloads use a five-day age gate with exact expiring human exceptions. See [languages and packages](docs/PACKAGES.md).

## Security and enterprise migration

Read [security boundaries](docs/SECURITY.md) and [enterprise hardening](docs/ENTERPRISE-HARDENING.md). Non-root containers, restrictive networking, separate controls, protected previews and provider privacy preferences are implemented. They do not make the local host or shared kernel an enterprise tenant boundary.

**GUI code can reuse its own Pi/Ori gateway capability.** Hiding the upstream key, checking headers or limiting messages cannot prove that only a coding harness called the model. Quick Python has no model access; native Coder headless execution has a separate inference boundary. An optional managed GUI harness design is documented, not deployed. Production identity, MCP policy enforcement and monitoring must be integrated with the enterprise application.

The assistant can read an explicit bounded collection of these documents and selected non-secret runtime settings when asked technical questions. It cannot use that reader to browse private files or environment credentials. Normal conversation stays focused on the user's task.

- [Interactive architecture field guide](reports/architecture/architecture.html) and [text guide](docs/ARCHITECTURE-GUIDE.md)
- [Azure implementation](docs/AZURE-IMPLEMENTATION.md) and [AKS scaling draft](docs/AKS-DRAFT.md)
- [Local scaling](docs/SCALING.md), [GUI harnesses](docs/GUI_HARNESSES.md) and [validation record](docs/VALIDATION.md)

Run `.venv/bin/python scripts/seed_architecture.py` once to add the labeled reference report to a fresh app. Existing saved app/artifact cards can be refreshed with `.venv/bin/python -m scripts.refresh_chat_cards --apply`; this preserves messages, item IDs and timestamps and never replays tools.

## Development and sharing

```sh
.venv/bin/python -m pytest tests -q
npm run test:polling
npx tsc --noEmit
npm run build
python3 scripts/repo_audit.py
```

The [sharing checklist](docs/GITHUB-READINESS.md) explains exact-index scanning and source-only exports. Personal conversations, generated user apps, artifacts, credentials, databases, private approval experiments and dependency caches remain ignored. The generic approval card renderer is included; the mock-email MCP server is not. Clean installs disable that experiment.

Preserve the included upstream Pi Chat license and attribution. Choose an organization-approved license before distributing the project beyond the team. The checked-in HTML is the generic reference guide, not an export of personal chat history.

Operational limits, deployment steps and retention ceilings are cataloged in [docs/LIMITS.md](docs/LIMITS.md). Public runtime defaults live in `config/limits.env`; private environment overrides stay out of Git.

Model routing and the temporary ZDR policy: [MODEL-ROUTING.md](docs/MODEL-ROUTING.md), configured in `config/models.env`.

Main chat supports OpenRouter Exa search with native ChatKit citations. See [model routing and search](docs/MODEL-ROUTING.md) for administrator controls.
