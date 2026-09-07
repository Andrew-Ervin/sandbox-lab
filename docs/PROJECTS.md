# Projects, workstations and file sharing

A project groups conversations and one shared headless coding environment. Ordinary chat does not allocate that environment. The first significant coding task claims or starts it; later project conversations share its files and installed packages, while retaining separate chat/agent histories. Active coding runs within one project are serialized.

A project can also link to one developer workstation. **Open in VS Code** creates or resumes that link. Existing developer workstations have project links, and new workstations receive a project automatically. This never assigns the developer workspace ID as the chat execution target.

The environments have separate Coder control planes, namespaces, home volumes, credentials, packages and processes. **Open in VS Code**, in a project chat or project page, creates/resumes the developer workstation, copies eligible source from its existing headless home, and opens that copied folder. No separate outbound copy button is needed. Projects without headless compute open the developer home without allocating a chat sandbox.

Copies are keyed by the source manifest. Reopening unchanged chat source reuses its existing developer copy without overwriting edits. Changed chat source creates a new import folder. This is a point-in-time handoff, not continuous mirroring. Active project coding must finish before a copy. Packages must be restored from manifests/lockfiles inside the developer environment. Its App preview uses the copied folder’s launch recipe; only one app server on port 3000 is supported per workstation. Recipes should use relative paths so they remain portable between homes.

## Returning developer changes

**Copy to chat** reads the developer folder opened by the handoff. Both environments must already exist. A review wakes sleeping environments and lists eligible source files, sizes, and whether they are new, matching or different from the destination's live files. Approval copies exactly the reviewed bytes into a new `.lab/imports/transfer_<id>` directory. It never overwrites live source. Ask your coding agent to inspect and deliberately merge the import, or merge it yourself. Packages must be restored from manifests/lockfiles inside the destination.

Limits: 2,000 files, 8 MB per file, 32 MB total, 10,000 scanned directory entries. Hidden credential paths, dependency trees, build output, symlinks and previous imports are excluded. Reviews expire after five minutes; the local broker holds at most two pending/preparing reviews. Each destination retains at most three import folders; another copy is refused until the user moves/removes an older one. There is no automatic deletion of previous source snapshots. Filename exclusions are not content inspection or full DLP.

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
