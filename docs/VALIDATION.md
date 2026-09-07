# Validation for the enterprise-hardening revision

Validated locally on macOS ARM64 with the existing kind/Calico/Coder installation. This is a record of checks, not a production security certification.

- Python suite: 72 tests, including gateway capability validation, expiry/authentication enforcement, enforced privacy, saved-reasoning compatibility without history mutation, blocked remote images, bounded request bodies, ownership, preview isolation, lifecycle, package gates, Git index secret checks and four bootstrap platform selections.
- OPA 1.8.0 example: 21 policy tests passed in a read-only, network-disabled container. No enterprise MCP integration is active.
- TypeScript checking and application production build passed; standalone architecture HTML rebuilt.
- Official pinned Rust, Go, .NET and Julia base-image digests include both AMD64 and ARM64. Verified bootstrap ran successfully on macOS ARM64, including pinned Ori/code-server downloads. Actual Linux/WSL2 clean installations have not run here.
- Live quick pod: non-root, read-only root, no model key/service-account token/host socket; internet, metadata, Kubernetes API and node access denied. Seven live Coder/broker namespace authorization checks passed.
- Live fresh Pi/Ori session: two real OpenRouter turns through the hardened gateway, file creation/read/update, same Coder workspace reuse and remembered marker. Required ZDR/data-collection policy remained enabled.
- Historical quota persistence checks are superseded: request-count quotas and the ledger have been removed. The retired native Coder provider was verified disabled with no stored API keys.
- Source audit excludes local state and known credentials. A source-only archive contains the architecture HTML and Azure Markdown, no .local/.env, personal conversations, user apps or Git history.

Saved-session compatibility: with the user's explicit approval, replayed an older synthetic Pi request to OpenRouter. The original request returned a 404 privacy-routing rejection; omitting historical reasoning fields from assistant messages before the latest user message returned 200 under the same mandatory ZDR/deny-data-collection policy. The gateway now makes that narrow outbound normalization for OpenAI models. Visible conversation content, tool calls/results, current-turn reasoning and stored Pi history remain intact; other providers' reasoning is unchanged. This isolates the triggering metadata, not the provider's internal routing implementation.

After deploying the fix, the older Pi/Ori session passed two live turns: create/read/update a file, reuse the same Coder workspace, and recall the prior marker. Routing was explicitly directed to the persistent project because a tiny Python task can correctly select quick compute. No privacy requirement was relaxed. Private diagnostic payloads/logs remain under ignored .local; none is included in the source archive.

The field guide's Managed Pi section and accompanying design document describe a **proposed** remote harness and trusted developer chat transport. They are not deployed controls. Their acceptance matrix is future validation; the current same-user model capability remains reusable by workspace code. The architecture reference was updated in place and the Apps gallery still contains four entries.

Full local logs and session identifiers stay under ignored .local or private docs/VERIFICATION.md. Re-run live smoke scripts deliberately: they consume model credit and create/update synthetic local conversations and workspace files.

## September 7 reliability follow-up

- 106 Python tests pass; TypeScript checks pass. Added artifact concurrency, deduplication, pinned-response eviction, cancellation, interrupted/oversized/checksum-failed download cleanup, grant reuse beyond former limits, and optional experiment checks.
- A fresh source-only archive starts and serves bootstrap without private experiment files; demo routes are absent by default. This local installation retains the mock-email experiment through an explicit ignored environment setting.
- Deployed PostgreSQL/cache services use Recreate; health probes have five-second timeouts, and PostgreSQL liveness checks process presence rather than connection readiness.
- Two live requests with the same legacy one-call credential both returned HTTP 200; missing credentials returned 403. No provider key was logged.
- Concurrent live package facade requests downloaded the six 1.17.0 wheel with matching SHA-256. All control services were ready after rollout.
- Source candidate audit passed. This checks known credential patterns/private paths; it is not a complete DLP guarantee.

## Projects follow-up

- Migrated 16 existing headless conversations to 16 project records, preserving workspace volumes and chat history; the migration is idempotent and a private pre-migration database backup is retained.
- Project tests cover migration, shared workspace allocation, stale metadata, ownership, safe nested reads, symlink/path rejection, mock sync replacement and failure retention, and project API ownership checks. The full prior 113-test suite passed; the additional project API test also passed. TypeScript checks passed.
- In the live UI, opened the existing Interactive Go Counter workspace, previewed main.go, and saved a mock OneDrive copy (nine files; five excluded entries). Created an empty conversation in that project and verified the shared-project banner. No Microsoft service was contacted.

### Collapsible project library

- TypeScript checks and backend tests cover owner checks, archive/restore across database restarts, stale thread saves, recency after migration, exact-name deletion confirmation, busy-job rejection, Coder deletion retries/410, and preserving the shared home when deleting an individual chat.
- Browser checked: one Projects heading, independent collapse control, five recent projects, project/chat menus, full library, and archive using a disposable empty project. Permanent deletion is verified with isolated databases and mocked Coder responses.

### Durable deletion and project refresh optimization

- 124 backend tests and TypeScript passed. Regression tests cover background completion without a browser, persisted operation recovery, failed-build manual retry, owner checks, read-only status, and constant-query project listing.
- Live UI test used a dedicated disposable project with two chats, a running Coder workspace, and seeded files. The exact-name confirmation submitted deletion, the dialog closed immediately, and cleanup completed across a page reload. Read-only checks verified Coder returned 410, the Kubernetes pod and PVC were absent, and test artifacts, quick checkpoint, mock sync and chat records were removed.
- Compared the original project IDs/names/workspace IDs and thread IDs against a local database backup: all 16 projects and 44 threads were preserved. Verification records remain under ignored `.local/`.
- Projects starts collapsed, the header still navigates to the full library, and the redundant View all projects link is removed.

### Visibility-aware refresh and bounded directory scanning

- 126 Python tests and seven browser-poll scheduler tests pass; TypeScript and the production build pass. Run scheduler tests with `npm run test:polling` (Node 22.13+).
- Scheduler tests exercise slow-request non-overlap, hidden/visible transitions, immediate catch-up, background status cadence, failure backoff/reset, dynamic intervals and cleanup during an outstanding request.
- A simulated million-entry directory stopped after 10,001 yielded entries with the production budget (the regression test uses a smaller budget), rather than materializing the directory. Browser listings report truncation; exports fail on the shared traversal budget. Existing symlink, ownership and previous-mock-copy retention checks pass.
- File previews retain binary download bytes when text decoding fails and no longer decode the same selected file on every status refresh.
- Live browser checks loaded developer workspace states, navigated back to an existing conversation with its chart and messages intact, and opened its four saved files. A full reload was needed after changing the custom hook structure during hot reload; the reloaded app navigated normally. No coding jobs, workspaces or conversations were created or deleted for these checks.

### Presentation, pagination and separate project/workstation sync

- 146 backend tests, seven polling scheduler tests, TypeScript and the production build pass. New coverage verifies bounded SQLite message pagination, foreign cursor/owner rejection, escaped and bounded file previews, project ownership, transfer expiry and link changes, busy-run rejection, checksum/path/symlink protections, and preserving live files and older imports.
- Live browser checks opened a Plotly chart and used its zoom control, rendered an SVG in the image viewer, and displayed five CSV rows in the embedded table viewer. Existing app/artifact cards use a consistent file header, type/size and compact preview/download actions.
- Real Coder SSH transport copied synthetic files from an existing headless workspace to an existing developer workstation and back into separate temporary import folders. Exact file bytes and unchanged originals were checked; all temporary fixture directories were removed. This exercised transport and import/export against real pods; the full review/approve flow is covered by isolated tests, not an approval click against user source.
- Linked all five existing developer workstations to project records. All five new project records still have no headless allocation. Existing 16 projects and 44 conversations, all 390 original message items, and non-widget message content were compared with a private backup and preserved. Only 103 widget payloads were refreshed; item identities and timestamps remain intact.
- Chat history now fetches only one page from SQLite. Secondary UI collections load on demand; ChatKit and conversation loads have placeholders. The local watcher excludes infrastructure, backend, report and test trees to avoid needless front-end reloads during non-UI work.
- Copies are human-reviewed source snapshots, not automatic mirroring: up to 2,000 files, 8 MB each, 32 MB total. Reviews expire after five minutes; there are at most two pending/preparing reviews globally and three retained import folders per destination. A fourth import is refused until the user moves/removes older imports. No older source is deleted automatically.
- The architecture reference HTML and Azure guide were refreshed in the existing reference app. The native Coder trial rollback snapshots retain these independent UI/project improvements.

### Final project, approval and assistant pass

- 168 Python tests, seven polling scheduler tests, package-policy UI checks, TypeScript and the production build pass. New tests cover provider failures inside HTTP 200, bounded documentation without secrets, large client pagination requests, lightweight dashboard projection, active jobs remaining visible, project-to-developer idempotency, and owned approval-payload previews.
- Browser testing resumed an existing developer workstation from its project, confirmed opening history collapses the right pane and vice versa, and verified the same IDE URL remained mounted on brief reopen. A 397-word synthetic email produced native confirm/cancel controls and an exact JSON side viewer. That request expired without approval. A second synthetic email exercised the refreshed presentation; no real email was sent and no human approval was submitted by automation.
- The earlier email attempt exposed a provider error body without `choices`; chat now presents a safe actionable failure. Another attempt exceeded the private mock service's 4,000-character bound, which is now declared in that tool's schema. The generic approval view has a bounded excerpt and long JSON values wrap when Fit width is enabled.
- Compared all original thread/project IDs and non-widget message JSON against the pre-review backup: preserved. Completed approval widgets were refreshed without tool execution. The architecture app's existing reference files were updated in place.
- The strict repository-wide lint preset is not clean. It includes compiled/upstream assets and first-party/template React-compiler, ARIA-style and type-aware findings. No claim of passing lint is made; functional checks and TypeScript pass. Review the lint scope and remaining findings before promoting this draft to a production baseline.
- No production load test or fresh Windows/Linux deployment was run. Local controls and bounded functional regressions are not evidence of enterprise capacity or tenant isolation.

- The same 168 tests also passed from a freshly extracted audited source archive, using the existing Python dependency environment but no copied `.env`, credentials or private experiment files. This verifies source independence, not a clean dependency/container installation.
- On the saved local data, the recent-run JSON portion of status fell from 458,872 to 64,596 bytes (about 86% smaller). This is a payload measurement, not a page-load or production latency benchmark.

- Request previews now provide formatted email and complete JSON views. Security tests cover HTML/script/attribute stripping, remote-image blocking, inline raster signatures and size bounds, and a CSP that permits only the trusted activity bridge. Browser verification switched Preview → JSON → Preview and confirmed the inline image, headings, recipients and schedule table render. The synthetic example is explicitly unsent and remains private local test data.


## One-click editor handoff and navigation refinement

- 177 Python tests and seven polling tests pass; TypeScript and the production build pass. Added coverage for deterministic source-copy reuse, preserving developer edits at the import cap, rejecting symlinked copies, scoped return exports, bounded editor folder URLs, and fast failure of a failed Coder build.
- Browser verification started a developer workstation directly from an existing Go project chat, automatically copied nine source files, opened the copied folder, and displayed main.go in VS Code with Pi Chat. The header action, preview-width menu, and exclusive history/preview controls were exercised. No model request or user source edit was needed.
- The cold-start test exposed two infrastructure limits: five retained developer PVCs exhausted the old 10 GiB quota, and native extension installation exhausted 256 MiB of /tmp. Local developer capacity is now configurable (40 GiB / 20 retained homes by default, still three running pods). GUI scratch is 1 GiB with a 2 GiB ephemeral-storage limit; headless scratch is unchanged. Failed builds stop preparation promptly, and extension installers are removed in a finally block.
- Open in VS Code is the explicit outbound source-copy action. Unchanged source reuses its existing developer copy without replacing editor edits; changed source creates a new copy, subject to the existing three-import limit. Copy to chat remains reviewed and reads the folder opened in the editor. Dependencies and execution remain separate.
- Updated the source documentation and existing architecture reference files without regenerating conversations. Private data and the MCP experiment remain excluded from commits.
