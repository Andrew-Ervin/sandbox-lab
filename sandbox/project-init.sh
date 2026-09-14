#!/bin/sh
set -eu
mkdir -p "$HOME/.cargo" "$HOME/.rustup" "$HOME/.cache" "$HOME/.local/bin" "$HOME/go"
if [ ! -e "$HOME/.rustup/toolchains/preinstalled" ]; then
  for toolchain in /opt/rust-toolchains/*; do
    rustup toolchain link preinstalled "$toolchain"
    break
  done
  rustup default preinstalled
fi
# User-installed versions and dependency caches live in the saved home.
