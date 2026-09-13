# Local setup

Use macOS or Linux, or Ubuntu in WSL2 on Windows. Install Node 22.13+ and Python 3.12. Docker is needed only for building custom Linux images locally, not for normal execution.

Copy `.env.example` to ignored `.env`, configure the model key and token signing secret privately, and use mode 0600. Run `bash scripts/download_tools.sh` for checksum-pinned uv, Ori and VS Code archives. Run `bash scripts/setup.sh` to install locked local dependencies. It does not provision cloud resources.

`python scripts/setup_azure_runtime.py --install --tools --prices` installs pinned Azure CLI/SDK into private environments and fetches public model pricing. Sign in with normal browser authentication using `sh scripts/azure_pilot_az.sh login --tenant <tenant-id>`. Do not use `--use-device-code` in a tenant whose Security Defaults block that flow. Configuration and token cache remain private. Do not copy another user's state. See [identity troubleshooting](IDENTITY.md#security-defaults-and-stale-sign-in-sessions) if a cached Microsoft account is rejected.

Review the templates in `infra/azure-sandbox-pilot/` before provisioning. Create sandbox groups with the operator's appropriate SandboxGroup Data Owner role. Set private `.local/azure-runtime/config.json` to the subscription, resource group, region, image IDs, storage account, reviewed cost model and resource profiles. Default-deny egress and short leases are mandatory for this pilot. ACR or dedicated-profile creation needs the user's fixed-cost permission. Creating a group quota does not allocate a running sandbox.

Start `.venv/bin/python scripts/start.py`, then open http://127.0.0.1:3000. Backend port 8787 and preview ports are loopback-only. A single launcher owns a runtime ledger; do not run two brokers against the same live workspace. Stop compute in the app before stopping the launcher, and verify cleanup through Azure if shutdown was interrupted.

Custom image recipes: `sandbox/Azure.Dockerfile` and `sandbox/Sessions.Dockerfile`. `scripts/prepare_azure_build.py` prepares a reviewed build context without live state. Images are imported into sandbox groups as disk images. Build dependencies follow the package-age policy. Windows/Linux clean-machine end-to-end validation remains outstanding.
