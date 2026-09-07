# Languages and package management

## The three environments

| Environment | Installed software | Writable dependency state | Reset behavior |
|---|---|---|---|
| Quick Python | Fixed image with Python, polars, NumPy, SciPy, scikit-learn, joblib and Plotly | Temporary run directory only; networking is denied | Pod destroyed after every run. Exported artifacts belong to the conversation and selected files are restored on later runs; Python variables and package installs do not survive. |
| AI project | Python, Node/npm, .NET SDK, Julia, Go, Rust/Cargo/rustup, GCC/G++, Clang, CMake, Bash/sh and ShellCheck | The project's own home PVC: source, venvs, package caches, lockfiles and build output | Stop/start retains files. Image updates retain files. Deleting a workspace removes its PVC according to the template lifecycle; stopping it retains the PVC. |
| Human developer | Same project toolchain image, plus VS Code and default Ori/Pi | The developer's own home PVC, independently managed | Same persistence, controlled by the developer through Coder Workspaces. |

An AI project is not the developer's workspace. There is no shared writable home or dependency cache between them. Reusing container image layers saves disk and startup time without sharing mutable project state. The selected headless harness (native Coder or optional Pi through Ori) issues commands in Coder workspaces using the ordinary language tools below; developers use the same commands from their terminal or through `ori-lab` / `pi-lab`. Developer harness configuration and sessions live in that developer's home volume. The human model credential expires after one hour; an Ori/Pi headless turn receives a new credential valid for eleven minutes. Neither has a request-count allowance. Pi session history persists in the owning home, independently of model credentials. Human refresh is available from Developer workspaces. Restart the Pi/Ori terminal after refreshing so its environment picks up the new capability.

## Returning to another conversation

Conversations in different projects have different homes. If project A installs Python package X and project B installs a conflicting version, their venvs and caches remain separate. Chats within the same project share that project home and lockfiles; use component-specific environments when they need incompatible versions. Returning to a chat reuses its project workspace. npm, uv, NuGet, Julia Pkg, Go modules, and Cargo each manage their own language environment inside that home; there is no single package manager replacing them all.

Quick compute deliberately uses a fresh Python process and a single-use pod for every call, drawn from a warm pool. It does not keep two long-running notebook kernels or install missing packages. A request for a missing package requires the AI to explicitly call delegate_project; the UI has no execution-mode selector. Ordinary Python computations avoid loading the chart renderer. Plotly show()/write_html() save an inline PNG plus a full HTML chart, with offline rendering inside the pod.

The host stores exported file versions under `.local/artifacts/<run-id>/`. SQLite’s conversation file catalog points to the latest version of each filename in that conversation. Older runs keep their original copies. Selected quick inputs are copied to `/workspace/files`; selected project inputs go to `/home/sandbox/project/chat-inputs`. These are copies, not mounts of the Mac or another workspace. Outputs must be saved in the environment’s artifacts folder to appear in chat and Conversation files. Regular quick working files are checkpointed locally per conversation and reseeded next run (40 files / 16 MB total; hidden files and dependency trees excluded). Variables and processes disappear with the pod. Project files remain in the Coder home even when they are not exported to chat.

The lab caps each exported file at 8 MB and each run or input transfer at 16 MB. Saved run versions currently have no automatic expiration; they consume host disk until explicitly cleaned up. Coder’s idle stop affects compute, not saved files. Lockfiles can recreate dependencies after deletion, but do not recover unsaved source or datasets.

The server owns active ChatKit response streams. Switching conversations, opening Apps, or closing the browser does not cancel work. Four quick executions and two headless project turns can run concurrently; up to eight chat jobs make progress, with additional admitted jobs queued. These defaults are configurable within the Kubernetes capacity budget. Same-conversation turns are serialized. Stop run cancels only that conversation. Results and job status are saved in SQLite; a server restart interrupts in-flight work and retains completed results. This is one local broker process, not a distributed crash-resuming job service.

## Per-language workflow

Run these in `/home/sandbox/project` or a subdirectory for the relevant component.

| Language | Project dependencies | Files to keep in Git | Workspace cache |
|---|---|---|---|
| Python | `uv init`, `uv add package`, `uv run script.py`; reproduce with `uv sync --locked`. Use `uv pip sync` for existing requirements files. | `pyproject.toml`, `uv.lock`, `.python-version`; or pinned requirements for `uv pip sync` | Project `.venv`; `~/.cache/uv` |
| JavaScript / TypeScript | `npm install`; reproduce with `npm ci`. TypeScript is a project package. | `package.json`, `package-lock.json` | Project `node_modules`; `~/.npm` |
| C# / .NET | `dotnet add package …`; `dotnet restore --use-lock-file`; reproduce with `dotnet restore --locked-mode` | `.csproj`, `packages.lock.json`, `global.json` to select an installed SDK | `~/.nuget/packages`; project `obj`/`bin` |
| Julia | `julia --project=.`; use `Pkg.add`, then reproduce with `Pkg.instantiate()` | `Project.toml`, `Manifest.toml` | `~/.julia` packages, artifacts and compiled cache |
| Go | `go get module@version`; `go mod download`; build/test normally | `go.mod`, `go.sum` | `~/go/pkg/mod`; `~/.cache/go-build` |
| Rust | `cargo add crate` or edit the manifest; `cargo build --locked` / `cargo test --locked` | `Cargo.toml`, `Cargo.lock` for applications, optional `rust-toolchain.toml` | `~/.cargo`; project `target`; `~/.rustup` for additional toolchains |
| C / C++ | GCC/Clang + CMake are preinstalled. Use vendored source and pinned local CMake dependencies. Conan/vcpkg feeds and arbitrary CMake downloads are not enabled. | `CMakeLists.txt`, presets, pinned dependency revisions and the chosen manager's lockfile | Project build directory and that manager's per-workspace cache |
| Shell | Bash/sh are preinstalled. Scripts call the other runtimes or explicitly installed user tools. ShellCheck is available. | Shell scripts and a documented/versioned list of external commands | `~/.local/bin` for user tools; no universal shell package lockfile |

`--system-site-packages` makes the scientific baseline immediately available to a Python project. For complete dependency independence, omit it and install the entire locked environment. Both approaches preserve their venv on that project's PVC. uv is preinstalled in the current image. The lab does not install pnpm, Bun, Conan or vcpkg automatically; those are deliberate project choices rather than invisible global changes.

## What is shared and what is rebuilt

The project image is the centrally maintained layer: Linux libraries, compiler/SDK versions and broadly useful Python packages. `sandbox/Dockerfile` defines it. The headless and developer templates use images built from that same layer. The developer image adds the IDE and default Pi/Ori integration. The quick image branches before the large toolchains.

Application dependencies belong in project manifests and lockfiles. Their caches persist in the workspace, but the lockfiles are the reproducible specification. Copy or clone a repository into another workspace and restore from those files; do not copy a live venv or `node_modules` between machines or architectures. The chat tool does not automatically synchronize a developer's workspace or mount it into an AI project.

New system packages, SDK prerequisites or OS-level tools require a reviewed image rebuild and Coder template update. Workspaces have no root/sudo and no general SDK/OS download route. The installed versions work offline. Language packages can install into the private home through their supported registry gateway; the five-day rule applies, without a package-name whitelist.

The persistent template allows 4 GiB RAM and 2 CPUs. Julia precompilation uses one worker; the smoke test also supplies `--heap-size-hint=1G`. The home PVC currently requests 2 GiB per workspace. Larger ML data, Julia artifacts, native builds or several SDK versions will require a larger workspace profile. On kind's local-path storage this number is not an enforced disk quota; monitor actual usage. Do not treat the lab's default as a production capacity plan. `/tmp` is limited ephemeral scratch space and does not survive a workspace restart.

## Downloads and security

Quick Python has no package download path. Adding a common quick dependency means rebuilding that image and replacing unused warm pods. A request needing another language, network downloads or persistent setup moves to an AI project.

Persistent workspaces use a read-only internal package gateway. Python uses uv throughout, including image builds and setup. uv, npm, Cargo, NuGet, Go and Julia clients are preconfigured to the gateway. All valid package names and transitive dependencies can be resolved, subject to the five-day age policy. Python/npm/Cargo/NuGet use registry publication dates. Go/Julia use first-observed quarantine because their content timestamps do not prove release age. Cold Go/Julia restores may therefore wait five days unless a human explicitly releases reviewed versions or hashes. C/C++ compilers are supplied by the image; additional libraries need an image change or approved source. Conan/vcpkg feeds and SDK downloads are not enabled.

Network & packages is a trusted human control: release one exact version/hash for 24 hours with an audit reason. No automatic exceptions are created. ConfigMap propagation can take about a minute. Existing installations and per-home caches remain usable; expiry prevents new gateway downloads, not execution of content already obtained.

The gateway verifies available hashes, limits downloads to 250 MB each and its public cache to about 700 MB, and persists resolved artifact IDs so npm lockfiles survive gateway restarts. It denies arbitrary URLs, CONNECT, query strings, uploads and client credential forwarding. Direct internet and external DNS are blocked by network policy; changing package-manager flags cannot bypass the gateway.

Package installation can execute build hooks. Those hooks run with the same restricted permissions as project code, inside the workspace. They can access that workspace's files and any credential deliberately supplied to it. Age filtering is not malware detection or an exfiltration guarantee. Approved model/search traffic still exists. There is no shared writable cache from which one project can poison another.

This Mac is ARM64/Linux inside Docker. C/C++ binaries, native npm modules, Python wheels, NuGet runtime assets and Julia artifacts must match the target architecture. Rebuild and restore for the actual AKS architecture instead of copying local binary caches. This .NET environment supports Linux console and ASP.NET applications; Windows-only WinForms/WPF and full .NET Framework require Windows environments.

## Verification and references

`scripts/smoke_languages.sh` compiles C/C++, then installs and executes a small dependency for Python, JS, Go, Rust, C# and Julia inside the headless Coder pod, and runs a shell script. It is a smoke test, not a guarantee that every package or native workload will fit the default resources.

- [uv project environments](https://docs.astral.sh/uv/guides/projects/)
- [Python virtual environments](https://docs.python.org/3/library/venv.html)
- [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci)
- [NuGet lock files](https://learn.microsoft.com/en-us/nuget/consume-packages/package-references-in-project-files#locking-dependencies)
- [Julia project environments](https://pkgdocs.julialang.org/v1/environments/)
- [Go modules](https://go.dev/ref/mod)
- [Cargo build and locked resolution](https://doc.rust-lang.org/cargo/commands/cargo-build.html)
- [.NET SDK installation without administrator access](https://learn.microsoft.com/en-us/dotnet/core/install/linux-scripted-manual)

## Opening an existing app

Open app resumes the owning Coder workspace and starts port 3000 from `project/.lab/app.json`. It does not send a chat message, run a model, or install dependencies. Source and packages come from the retained home. Legacy static/Go/npm apps can have their startup recipe inferred once. App previews are a process in the development workspace, not a separate deployment. Closing the view lets preview leases and then workspace idle timers expire.


## Current lifecycle and security revision

Quick reserve: five idle minutes, unassigned to any conversation. Used pods are destroyed. Quick source, artifacts and bounded working-file snapshots persist locally; no cloud storage is configured. A multi-language Coder project is allocated only when the AI calls `delegate_project`. AI projects stop after five idle minutes, human workstations after ten, subject to active work and recent visible interaction. Background connections and status polling do not count. Pi Chat defaults to the right secondary sidebar and uses Ori → Pi → the trusted OpenRouter gateway. There is no package-name whitelist; only exact, expiring age exceptions. Live pod snapshots refresh every five seconds. See [the updated field guide](ARCHITECTURE-GUIDE.md) for enforcement, data paths, local credential scope and production gaps.

Artifact downloads stream to temporary files in 64 KiB chunks. Two downloads may run concurrently, while same-artifact requests share a per-artifact lock. Cache reservations and completed artifacts share a 700 MB budget; files remain pinned throughout serving and cannot be evicted mid-response. Registry checksums are checked before atomic publication where provided (Go/Julia retain their existing verification paths). Partial downloads are removed on failure/cancellation and at single-writer startup. The 250 MB artifact limit and five-day age policy remain in force.
