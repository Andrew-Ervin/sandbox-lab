ARG PYTHON_BASE=sandbox-lab/sessions-python:pilot-20260912
FROM rust:slim-bookworm@sha256:1469a27c125cb5a3aebfa4f4e4665d935b02fb72cc093b2c974b3d740e43f157 AS rust
FROM golang:bookworm@sha256:648f440f42a0958804efb24df176f806f9d353b41f1c0627f666428e40310f6b AS go
FROM mcr.microsoft.com/dotnet/sdk:10.0@sha256:e1ffd2a92ae84c1291bc1b6887501f8af98e6331e7af6d4c8d37168c5e87a64c AS dotnet
FROM julia:1-bookworm@sha256:709daad7eccdb0363b080df203601988cff8c6a9581162668b76804cca407888 AS julia
FROM ${PYTHON_BASE} AS base
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

FROM project AS azure-headless
USER root
FROM developer AS azure-developer
USER root
