#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in node npm python3; do
  if ! command -v "$tool" >/dev/null; then echo "Missing prerequisite: $tool. See docs/LOCAL-SETUP.md"; exit 1; fi
done
node -e "const [major,minor]=process.versions.node.split('.').map(Number);if(major<22||(major===22&&minor<13))throw Error('Node 22.13+ required')"
if [[ ! -x .local/bin/uv || ! -x .venv/bin/python ]]; then echo 'Run bash scripts/download_tools.sh first.'; exit 1; fi
if [[ ! -s .env ]]; then echo 'Copy .env.example to .env, fill in OPENROUTER_API_KEY and LAB_TOKEN_SECRET, and chmod 600 .env.'; exit 1; fi
if [[ $(uname -s) == Darwin ]]; then
  mkdir -p .runtime.nosync/js
  cp package.json package-lock.json .runtime.nosync/js/
  npm --prefix .runtime.nosync/js ci
  if [[ ! -e node_modules ]]; then ln -s .runtime.nosync/js/node_modules node_modules; fi
else
  npm ci
fi
.venv/bin/python scripts/package_pi_chat.py
.venv/bin/python scripts/download_editor_extensions.py
.local/bin/uv pip sync --python .venv/bin/python backend/requirements.lock
echo 'Local dependencies ready. Configure private Azure settings with scripts/setup_azure_runtime.py. Cloud provisioning is explicit; see docs/LOCAL-SETUP.md.'
