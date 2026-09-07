#!/bin/sh
set -eu
mkdir -p "$HOME/.cargo" "$HOME/.rustup" "$HOME/.cache" "$HOME/.local/bin" "$HOME/go"
if [ ! -f "$HOME/.rustup/settings.toml" ]; then
  for toolchain in /opt/rust-toolchains/*; do
    rustup toolchain link preinstalled "$toolchain"
    break
  done
  rustup default preinstalled
fi
# User-installed versions and dependency caches live on the workspace PVC.
