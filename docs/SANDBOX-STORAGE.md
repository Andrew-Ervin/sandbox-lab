# Sandbox storage and startup policy

Active/recent environments retain native Memory suspend for ten-minute idle shutdown. Suspended sandboxes release compute; retained disk/memory is storage, not an idle replica CPU charge. The broker keeps one clean standby per recently used role for ten minutes. A shared disk image is separate from each user's saved home; do not build an image for each project.

## Seven-day home archival

The private runtime setting `archive_after_days: 7` enables a broker maintenance task. It considers only stopped, non-disposable headless/developer workspaces with no activity for seven days. It processes one home at a time under the workspace lifecycle lock and respects the compute budget. The broker must be running; missed work is considered on the next run.

The task resumes the old sandbox briefly, freezes existing sandbox-user processes, and archives the saved home. It uploads immutable, hashed chunks and a manifest to the existing private Blob account, then downloads and verifies every byte. Only after verification does it remove the original sandbox. The workspace ID, ownership, app records and conversation history remain. Next open downloads the archive, verifies it, creates compute from the configured image and restores the home before readiness. A private local recovery copy is retained too. An ambiguous deletion is reconciled by checking the original sandbox before restoring.

This is **file archival**, not export of an Azure memory snapshot. Saved files, dotfiles, installed home packages and settings survive; running processes, `/tmp`, and other state outside the home do not. The image-owned Rust toolchain link is recreated from the image. Other external symlinks cause archival to stop without deleting the source. User-selected extra mounts are not supported by this archival policy.

Pilot safeguards: 600 MB maximum compressed home, the existing aggregate 1 GB Blob checkpoint allowance, 100 checkpoint objects, and 2 GB weekly attempted uploads. Base64 transport counts against those allowances. Oversized or failed archives retain their sandbox and report a failure; retry is deferred for a day. Archives are not silently expired or purged. These limits are intentionally below a production storage service's capacity and can prevent archival when many objects accumulate.

The task does not create a new registry, volume, storage account, timer service, or fixed-price infrastructure. The existing Hot LRS account is used for immediate restore. Azure Blob Archive tier is inappropriate for interactive reopen; selecting Cool/Cold should follow expected retention and retrieval economics, not simply the age of a workspace.

## Why not move native snapshots into Blob?

The documented native snapshot API and installed SDK support create/get/list/delete and restoring a sandbox from a snapshot. They do not expose a full snapshot export into a customer Blob account. Native snapshots remain useful for fast process-state resume, but are region-scoped and retain their compute tier. Snapshot clones cannot be resized at restore. A file archive can rebuild into a different configured tier, with the cost of cold initialization.

Blob-backed volumes are useful for shared artifacts and bulk data. A data-disk volume serves high-I/O working sets but attaches to only one sandbox. Keep source builds, dependency trees, SQLite and editor state on a local filesystem unless a measured volume experiment justifies a change. The existing three-way project sync handles conflicting edits; mounting the same Blob path into both environments would not solve concurrent-write conflicts.

## Startup improvements and evidence

Small execution requests write and launch in one SDK call. Bootstrap combines directory initialization with bundle-version checking and combines bridge credential installation with its launch. Credentials still rotate and isolation controls stay intact. App previews skip editor configuration and reuse healthy processes. Root-relative HTML, module and CSS asset URLs are scoped to the opaque preview capability; this fixes a Vite page that returned HTML but rendered blank. Opaque app-frame POST requests require the same valid capability path; unrelated origins remain denied and editor authentication is unchanged.

A fresh synthetic headless environment reached execution readiness in 4.24 seconds and completed a file write plus code execution in 4.98 seconds. Its measured allocation was 0.93 seconds and bootstrap 2.98 seconds. This is one local pilot measurement, not a service SLA or concurrent-load percentile. Warm claims avoid allocation/bootstrap, but still verify the broker connection. Native memory resume preserves expensive application initialization; aggressively archiving recently used environments would undermine that benefit.

References: [Azure snapshot lifecycle](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-snapshots-state-management), [sandbox volumes and tiers](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-overview), [Blob pricing](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/).

Saved app listings read local metadata immediately while cloud inventory and health refresh in the background. Pending observations are marked stale and do not assert readiness; opening still checks the runtime.

Archive reopen retries reuse the verified local transfer. Explicit workspace deletion removes archive chunks before their manifest and then local transfer files; a failed cleanup remains retryable. Azure Blob soft-delete/version retention can retain recoverable bytes for the configured retention period. App-only resumes defer code-server and editor profile initialization until an editor is requested.
