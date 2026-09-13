#!/bin/sh
# Azure CLI isolated from the application Python environment and global login.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export AZURE_CONFIG_DIR="$repo/.local/azure-pilot/azure-config"
export AZURE_CORE_COLLECT_TELEMETRY=0
export AZURE_CORE_LOGIN_EXPERIENCE_V2=off
exec "$repo/.local/azure-pilot/az-venv/bin/az" "$@"
