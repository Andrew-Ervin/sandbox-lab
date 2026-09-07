FROM node:22-bookworm-slim AS node
FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM rust:slim-bookworm@sha256:1469a27c125cb5a3aebfa4f4e4665d935b02fb72cc093b2c974b3d740e43f157 AS rust
FROM golang:bookworm@sha256:648f440f42a0958804efb24df176f806f9d353b41f1c0627f666428e40310f6b AS go
FROM mcr.microsoft.com/dotnet/sdk:10.0@sha256:e1ffd2a92ae84c1291bc1b6887501f8af98e6331e7af6d4c8d37168c5e87a64c AS dotnet
FROM julia:1-bookworm@sha256:709daad7eccdb0363b080df203601988cff8c6a9581162668b76804cca407888 AS julia
FROM python:3.12-slim-bookworm AS base
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates tini procps chromium && rm -rf /var/lib/apt/lists/*
RUN uv pip install --system --no-cache polars==1.34.0 numpy==2.3.3 scipy==1.16.2 scikit-learn==1.7.2 plotly==6.3.1 joblib==1.5.2 kaleido==1.1.0
RUN groupadd -g 1000 sandbox && useradd -m -u 1000 -g 1000 -s /bin/bash sandbox && mkdir -p /workspace /opt/lab && chown 1000:1000 /workspace
ENV HOME=/home/sandbox PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /workspace
COPY --chmod=755 sandbox/chromium-for-plots /opt/lab/chromium-for-plots
ENV BROWSER_PATH=/opt/lab/chromium-for-plots
FROM base AS project
USER root
RUN apt-get update && apt-get install -y --no-install-recommends build-essential clang cmake pkg-config libssl-dev ripgrep libicu72 libgssapi-krb5-2 zlib1g shellcheck && rm -rf /var/lib/apt/lists/*
COPY --from=go /usr/local/go /usr/local/go
COPY --from=rust /usr/local/cargo/bin /usr/local/cargo/bin
COPY --from=rust /usr/local/rustup/toolchains /opt/rust-toolchains
COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet
COPY --from=julia /usr/local/julia /usr/local/julia
ENV PATH=/home/sandbox/.local/bin:/home/sandbox/go/bin:/home/sandbox/.dotnet/tools:/usr/share/dotnet:/usr/local/julia/bin:/usr/local/cargo/bin:/usr/local/go/bin:$PATH
ENV CARGO_HOME=/home/sandbox/.cargo RUSTUP_HOME=/home/sandbox/.rustup GOPATH=/home/sandbox/go GOMAXPROCS=2 CARGO_BUILD_JOBS=2
ENV DOTNET_ROOT=/usr/share/dotnet DOTNET_CLI_HOME=/home/sandbox DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 NUGET_PACKAGES=/home/sandbox/.nuget/packages JULIA_DEPOT_PATH=/home/sandbox/.julia JULIA_NUM_THREADS=2 JULIA_NUM_PRECOMPILE_TASKS=1
COPY sandbox/project-init.sh /opt/lab/project-init.sh
USER 1000:1000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sleep", "infinity"]
FROM project AS ai
ARG TARGETARCH
USER root
RUN npm install -g @earendil-works/pi-coding-agent@0.85.1 && npm cache clean --force
COPY .local/bin/ori-linux-${TARGETARCH} /usr/local/bin/ori
RUN chmod 755 /usr/local/bin/ori
COPY sandbox/agent.py /opt/lab/agent.py
COPY sandbox/harness_setup.py /opt/lab/harness_setup.py
COPY sandbox/package_setup.py /opt/lab/package_setup.py
ENV PI_TELEMETRY=0 ORI_TELEMETRY=0 ORI_NO_UPDATE_CHECK=1
USER 1000:1000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sleep", "infinity"]
FROM ai AS developer
ARG TARGETARCH
USER root
COPY sandbox/pi-chat /opt/lab/pi-chat
COPY .local/bin/code-server-linux-${TARGETARCH}.tar.gz /tmp/code-server.tgz
RUN tar -xzf /tmp/code-server.tgz -C /opt && ln -s /opt/code-server-4.106.3-linux-${TARGETARCH}/bin/code-server /usr/local/bin/code-server && rm /tmp/code-server.tgz
USER 1000:1000
FROM base AS quick
COPY sandbox/checkpoint.py sandbox/collect.py sandbox/quick.py sandbox/plot_capture.py sandbox/render_plot.py /opt/lab/
USER 1000:1000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sleep", "infinity"]
