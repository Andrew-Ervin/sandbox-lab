# Projects, workstations and file sharing

A project groups conversations and one shared headless coding environment. Ordinary chat does not allocate that environment. The first significant coding task claims or starts it; later project conversations share its files and installed packages, while retaining separate chat/agent histories. Active coding runs within one project are serialized.

A project can also link to one developer workstation. **Open in VS Code** creates or resumes that link. Existing developer workstations have project links, and new workstations receive a project automatically. This never assigns the developer workspace ID as the chat execution target.

The environments have separate Coder control planes, namespaces, home volumes, credentials, packages and processes. **Open in VS Code** creates/resumes the developer workstation, synchronizes eligible project source, and opens its working folder. **New chat in project** automatically brings developer source into the separate headless home before the chat starts. Neither flow requires a copy/review step. An empty developer-only project does not allocate headless compute until it has source to continue or the assistant delegates a coding task.

## Ongoing source sync

While both linked environments are running, the trusted local broker compares source manifests every **15 seconds** (`PROJECT_SYNC_SECONDS`). It also checks on handoff and after a chat turn. Sleeping environments stay asleep during background checks; opening either side catches up its files. Sync does not count as user activity or defeat idle shutdown. Active chat coding holds the project lock, so background copying waits for that run to finish.

A last-common hash per file identifies which side changed. One-sided edits, new files and tracked deletions propagate automatically. If both sides changed a file, both versions remain and the project displays **Keep chat** / **Keep VS Code** choices. Destination hashes are checked again before atomic file replacement. The baseline and status survive backend restarts. Failed or oversized reads are not treated as deletions.

Fresh projects synchronize their project roots. Older snapshot-based projects continue in their previously selected import folders. Ongoing sync updates those same folders; it does not accumulate a snapshot on every pass. Unselected legacy import folders are excluded and retained until explicitly removed.

Limits: 2,000 files, 8 MB per file, 32 MB total, 10,000 scanned entries, two transfer operations. Dependency trees, hidden credential paths, build output, symlinks and recursive imports are excluded. Filename exclusions are not content inspection or full DLP. Credentials, installed packages, processes and unsaved editor buffers are not synchronized. Restore dependencies from manifests/lockfiles in each environment using its package gateway. Its app preview uses that environment's source/launch recipe; one app server on port 3000 is supported per workstation.

This is eventual file synchronization, not a transactional project filesystem or a collaborative editor. Avoid editing the same files concurrently; saved multi-file changes can be observed partway through. A running dev server may need a rebuild/restart after source changes. For production, use Git revisions, distributed leases and a durable sync queue with audited conflict handling; see `AZURE-IMPLEMENTATION.md`.

Mock sync to OneDrive saves a separate bounded local mirror under ignored local state. No Microsoft service is contacted. Azure Blob, OneLake and OneDrive integrations remain proposals.

## Browsing and lifecycle

Apps, files and VS Code open in the right pane. Opening it collapses history; reopening history collapses the preview. The right-hand **Reopen preview** control restores a briefly collapsed iframe without restarting it. Preview sizing, fit, reload and external opening live in its options menu. The history collapse control is inside the sidebar header; resizing remains available by dragging its edge. Collapsed views do not renew the preview lease. App servers still run in the same execution container where their source lives and follow its idle policy.

The current defaults are five idle minutes for headless compute, ten for developer workstations, and two for unused preview listeners. Active runs/setup and recent visible interaction protect their relevant environment. Status polling is read-only and does not count as activity. Local overrides are reported by the assistant's documentation tool and Lab status.

Deleting a project removes its chats and headless home; an independently linked developer workstation is retained and unlinked. Deleting a workstation retains its project and separate headless environment. Permanent deletion uses the existing confirmation flow.

## Assistant and saved presentation

The main assistant uses everyday language unless implementation detail is requested. It can retrieve selected sections from curated operator documentation plus an explicit list of non-secret runtime settings. It cannot use that reader to inspect `.env`, private operator state, or arbitrary files.

Approval requests use a formatted summary, native ChatKit confirm/cancel controls, and a request viewer with Preview and JSON tabs. Email previews retain text structure and embedded raster images, including Microsoft Graph-style inline attachments. External images, active content, links and custom HTML styles are disabled; this is a safe content preview rather than an exact reproduction of every email client. The complete payload is bounded to 1 MB. The full payload is the source of truth; opening it cannot approve the action. Completed approval cards collapse. Actual authorization and mandatory approval enforcement belong to the tool service; the generic renderer does not enforce OPA or supply enterprise identity.

Saved chat presentation can be rebuilt without model calls:

```sh
.venv/bin/python -m scripts.refresh_chat_cards          # preview the number of changes
.venv/bin/python -m scripts.refresh_chat_cards --apply  # backup and update presentation
```

This updates supported saved widgets, keeping original messages, item IDs/timestamps and artifact files. It does not regenerate an assistant's old prose. A private experiment can register its own presentation migration; clean installations need no experiment files. Reload an open conversation after applying changes.


Main chat can search through OpenRouter’s Exa server tool when the administrator enables it. Provider source annotations become native ChatKit citations, including the Sources panel, and persist with the saved answer. Title generation does not search.

Internal app and artifact links open the authenticated side preview through native ChatKit deeplinks. Open app in the project chat header stays available while a later coding run edits the same project; the older saved card remains in history.

### App dependencies after source sync

Node app previews started with an npm launch recipe restore dependencies automatically: `npm ci` when a package lock exists, otherwise `npm install` to create one. The restore goes through the existing package gateway and release-age policy. A manifest/lockfile digest avoids repeating it when unchanged; missing `node_modules` always restores. The marker and packages stay in that workspace's home. Failed installs expose an app-start error rather than silently bypassing package policy. Other languages should use a self-restoring launch command (`uv run`, `go run`, `cargo run`, `dotnet run`) or an explicit project startup script; the preview service does not copy their installed environments.
