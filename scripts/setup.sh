#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in docker kubectl node npm python3; do
  if ! command -v "$tool" >/dev/null; then echo "Missing prerequisite: $tool. See docs/LOCAL-SETUP.md"; exit 1; fi
done
node -e "const [major,minor]=process.versions.node.split('.').map(Number);if(major<22||(major===22&&minor<13))throw Error('Node 22.13+ required')"
if ! docker info >/dev/null 2>&1; then echo 'Start a Linux Docker engine (Docker Desktop on Mac/Windows, or Docker Engine on Linux).'; exit 1; fi
if [[ $(docker info --format '{{.OSType}}') != linux ]]; then echo 'Switch Docker to Linux containers.'; exit 1; fi
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
.local/bin/uv pip sync --python .venv/bin/python backend/requirements.lock
if ! .local/bin/kind get clusters | grep -qx sandbox-lab; then
  .local/bin/kind create cluster --config infra/kind.yaml --kubeconfig .local/kubeconfig --image kindest/node:v1.35.0
fi
kubectl --kubeconfig .local/kubeconfig apply -f .local/research/calico.yaml
kubectl --kubeconfig .local/kubeconfig -n kube-system rollout status daemonset/calico-node --timeout=240s
for target in quick project ai developer; do docker build --target "$target" -t "sandbox-lab/$target:local" -f sandbox/Dockerfile .; done
docker build -t sandbox-lab/egress:local -f sandbox/Proxy.Dockerfile .
docker build -t sandbox-lab/gateway:local -f sandbox/Gateway.Dockerfile .
docker build -t sandbox-lab/packages:local -f sandbox/Package.Dockerfile .
.local/bin/kind load docker-image sandbox-lab/quick:local sandbox-lab/project:local sandbox-lab/ai:local sandbox-lab/developer:local sandbox-lab/gateway:local sandbox-lab/packages:local sandbox-lab/egress:local --name sandbox-lab
.venv/bin/python scripts/render_infra.py
kubectl --kubeconfig .local/kubeconfig apply -f infra/lab.yaml
.venv/bin/python scripts/apply_secrets.py
.venv/bin/python scripts/broker_credentials.py
echo 'Infrastructure ready. Run .venv/bin/python scripts/start.py; see README.md for first-time Coder initialization.'
