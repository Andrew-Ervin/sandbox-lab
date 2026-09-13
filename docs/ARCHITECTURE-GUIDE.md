# Architecture field guide

The React/ChatKit interface talks to one local FastAPI broker. The broker stores conversations, queues work and calls OpenRouter. It uses Azure Sandboxes for isolated execution and private Blob for checkpoints.

Quick Python receives selected inputs and per-chat working files, executes in a fresh interpreter, exports artifacts, checkpoints allowed files and deletes its sandbox. Headless coding runs in the project's persistent sandbox with model reasoning in the broker. Developer VS Code and Pi/Ori run in a separate home with a scoped GUI model capability. Generated apps run inside their owning sandbox and are exposed through authenticated relays to isolated local preview origins.

Project chats share their headless source. Linked workstations synchronize eligible source through three-way hashes, preserving conflicts for a user decision. Status reads never wake compute. One clean spare per recently active role reduces setup latency and drains after ten idle minutes; persistent homes suspend rather than being reassigned.

See the standalone interactive [field guide](../reports/architecture/architecture.html), [scaling](SCALING.md), [security](SECURITY.md), and [projects](PROJECTS.md). The field guide is source-only and requires no network requests to render.
