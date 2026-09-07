# Local setup: Windows, Linux and macOS

The application runs Linux Kubernetes containers. The bootstrap selects pinned host tools and matching ARM64/AMD64 Linux image assets. Downloads are SHA-256 checked using `scripts/tool-downloads.lock.json`; arbitrary `latest` Ori downloads have been removed. Native caches/venvs are not portable between architectures: rebuild images and recreate environments on the destination machine.

## Supported setup paths

| Host | Container engine | Run project commands in |
|---|---|---|
| Windows 11 / supported Windows 10 | Docker Desktop with WSL2 integration and Linux containers | Ubuntu inside WSL2; store the repo under `~/src`, not `/mnt/c` |
| Linux AMD64/ARM64, glibc distribution | Docker Engine with working non-root access, or Docker Desktop | Bash/Linux terminal |
| macOS Apple Silicon/Intel | Docker Desktop | Bash/zsh; scripts use Bash explicitly |

Native Windows Python/PowerShell is not supported by the process supervisor, SSH tooling or symlink setup. WSL2 is the Windows compatibility path, not a Windows container image. From administrator PowerShell, install WSL with `wsl --install`, restart if prompted, install Ubuntu, and enable Docker Desktop integration for that distribution. Then follow all remaining steps in the Ubuntu terminal. [Microsoft WSL installation](https://learn.microsoft.com/en-us/windows/wsl/install).

Prerequisites: Git, Bash, Python 3.9+ for the bootstrap, Node **22.13+**, npm, kubectl compatible with Kubernetes 1.35, and a working Linux Docker engine. The bootstrap uses pinned uv to create a Python 3.12 virtual environment (uv can download that interpreter). Allow substantial disk space for scientific libraries, multiple SDKs, Chromium and VS Code. A practical starting point is 4–8 CPUs, 12–16 GiB memory and 40+ GiB free Docker disk; tune to your machine and the concurrency defaults. These are setup estimates, not production sizing.

## Fresh checkout

```sh
# Clone the shared source into a normal local directory first.
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
# Privately edit .env: supply a NEW OpenRouter key and the generated LAB_TOKEN_SECRET.
# Do not paste either value into source, command history, or an issue.
bash scripts/download_tools.sh
bash scripts/setup.sh
```

The local key/domain settings are not enterprise authentication. Privacy routing now requires a ZDR-eligible provider for the chosen model and denies providers collecting data. Requests fail if no compatible provider is available; do not weaken the control to pass a smoke test. `LAB_ALLOW_WEB_SEARCH=true` preserves the lab's approved Exa search; set false for projects where search disclosure is inappropriate, apply secrets and restart the gateway.

All Kubernetes commands in scripts use `.local/kubeconfig`; normal user kubeconfig is not replaced. Use the default local Docker context matching the host architecture. Cross-builds require fetching both sets of assets explicitly and testing native dependencies; the bootstrap intentionally does not silently run emulated mixed-architecture workspaces.

In terminal A, keep the two Coder port forwards running:

```sh
.venv/bin/python scripts/forward_coder.py
```

In terminal B:

```sh
.venv/bin/python scripts/setup_coder.py
.venv/bin/python scripts/setup_coder.py --ai
.venv/bin/python scripts/publish_templates.py
.venv/bin/python scripts/configure_agents.py
```

Stop terminal A's forwarding process with Ctrl-C, then launch the application (which owns the same forwards):

```sh
.venv/bin/python scripts/broker_credentials.py
.venv/bin/python scripts/start.py
```

Open http://127.0.0.1:3000. Create a developer workspace through the sidebar when needed. Refresh Ori/Pi after its one-hour capability expires; chat projects receive a fresh capability per turn. The separate Coder developer portal is on 7080. Do not expose these local ports to a LAN as a multi-user service.

To add the documented example without importing anyone's chats/apps:

```sh
.venv/bin/python scripts/seed_architecture.py
```

This creates only the explicitly labeled architecture reference conversation and static app from checked-in files. There are no personal conversation exports in the shared source. Rebuild its standalone HTML after editing with `node scripts/build_embeds.mjs report`.

## Existing installations

Preserve `.local`, `.env` and PVCs. `setup.sh` reapplies infrastructure and rebuilds images; it does not intentionally delete project homes. Stop the backend before planned changes that interrupt jobs. Image changes take effect when workspace pods restart. Refresh developer capabilities and restart existing Pi/RPC sessions after model-gateway authentication changes.

macOS keeps Python/frontend dependencies in `.runtime.nosync` behind symlinks to avoid cloud file eviction. Linux/WSL uses conventional `.venv` and `node_modules` directories. Do not copy these dependency directories, the kind cluster, or private `.local` state to create another user's installation.

## Validation and portability limits

```sh
.venv/bin/python -m pytest tests -q
npx tsc --noEmit
npm run build
.venv/bin/python scripts/repo_audit.py
```

`download_tools.py --dry-run --system linux --arch amd64` verifies the selected asset plan without downloading or changing anything. The bootstrap has tests for all four host/architecture combinations. This revision was exercised on macOS ARM64; **Windows/WSL2 and Linux clean-machine installs still require validation on those hosts**. The manifest and binary selection changes are not a claim that those full smoke tests have run.

## Optional private email approval experiment

Clean installations default `LAB_ENABLE_MCP_EXPERIMENT=false` and do not need private `.local/mcp-approval-experiment` files. Chat, developer setup and the standard Ori/Pi headless runner work without them. This installation explicitly enables the flag in its ignored `.env` to retain the existing mock-email test. If explicitly enabled with missing files, startup reports how to disable it. No demo implementation or credentials are included in source exports.
