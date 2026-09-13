# Validation record

The Azure-only refactor is validated with the Python suite, polling tests, TypeScript and production build. Live test receipts, latency/cost estimates and diagnostic logs remain in ignored local state. They are not source artifacts.

Meaningful live checks cover an actual computation, headless file creation and execution, app rendering, VS Code opening, Pi Chat response, source checkpointing and stop/resume. HTTP 200 alone does not prove the editor extension, app rendering or inference route works. Test concurrently with bounded synthetic requests and report failures as well as successes.

Current limits: tenant sign-in on a single local broker; one broker process; finite SDK/command concurrency; provider/API preview; delayed Azure billing; no 100/100/500 simultaneous-user validation; no distributed scheduler or public production preview gateway. Source sync is eventual and excludes credentials, dependencies and unsaved buffers. GPU and shared production storage require a separate reviewed deployment.

Required checks: `.venv/bin/python -m pytest -q`, `npm run test:polling`, `npx tsc --noEmit`, `npm run build`. `node scripts/build_embeds.mjs report` regenerates the standalone architecture artifact. Preserve backups before presentation or metadata migrations. Run the exact-index privacy audit before commits.

Live verification on 2026-09-13: the Python suite passed 256 tests (48 dependency/widget deprecation warnings); all seven polling tests, TypeScript checking, the production build and the standalone report build passed. Nine bounded synthetic environments ran concurrently: three Python, three headless and three developer environments each wrote/executed code and returned the correct sum of squares. This is not a 700-session load test.

The existing developer workstation rendered Pi Chat, Claude Code and Codex. Each performed an actual shell computation through Ori and returned 338350. Claude's one-command approval remained enabled. The pinned marketplace packages activated; gallery search returned approved results. A normal headless coding API request wrote and executed a file, and the generated supply-chain app visibly rendered through the app catalog. Python execution was also checked in the chat UI earlier in the run.

Remaining live observations: fresh ChatKit frames in the Codex in-app browser were rejected with `net::ERR_BLOCKED_BY_CLIENT` for the hosted CDN frame. The app now reports this loading failure instead of showing an indefinite spinner; API execution and other app pages remain available. Browser policy was not bypassed. Claude's native panel displays an `Unsupported content type: redacted_thinking` warning for some OpenRouter responses, although its text and tool execution completed. These are not reported as fully passing UI paths.

After the final local restart, both previously used developer workstations resumed. The dev editor restored Claude and Pi conversations, the Codex sidebar loaded, and its approved gallery search returned exactly one Claude result. The gallery pagination and immutable-ID workspace-resume fixes are deployed. The standalone report was visually inspected; card text contrast was corrected and its artifact rebuilt.

Follow-up verification: a disposable 1 CPU / 2 GiB workstation resized to 2 CPU / 4 GiB in 17.91 seconds and retained a file in its home. Both disposable cloud instances were removed after the check. Initial restore failures were traced to image-owned directories; replacement now restores into a fresh user-owned home using unprivileged extraction. Authentication tests cover signed token validation, tenant/audience/nonce/expiry rejection, browser-bound single-use sign-in state, cross-owner workstation denial and logout revocation. The final suite passed 272 tests, plus all seven polling tests, TypeScript, the production build and the regenerated standalone report.

Entra sign-in completed in the browser. Migration preserved the original 35 threads, 255 items, 11 projects, 24 runs and 35 file records; backups remain private. The accepted multiword workstation name reopened successfully and moved to the top of the workspace list. Dark Modern selected in one editor appeared in the existing dev workstation, whose native Claude/Pi conversations remained present. The original light selection was restored after testing.

Two existing apps resumed in 7.235 and 7.692 seconds, with repeated open endpoint calls at 0.142–0.360 seconds. These are backend timings, not full visual-load percentiles. The supply-chain app rendered with map, controls and connected solver service through the signed-in iframe. Generated-app previews use opaque frames and a short-lived capability path for their document, assets, and websocket relay, so they do not receive or share the trusted application's authentication cookies. Artifacts retain their opaque origin policy. Connection reuse explicitly rejects upstream cookies.

Signed-in ChatKit Python execution returned 338350. A headless coding run wrote and executed account_check.py and returned 338350. Its verification project was archived, retaining files/history. The earlier ChatKit client-block observation did not recur in these browser checks; no browser policy bypass was used.

Direct editor listeners now use a ten-minute lease, renewed by actual visible-editor input and model activity. The editor reports personal preference changes and layout separately from user activity. This avoids the former two-minute preview disconnect while retaining idle suspension.

A subsequent real-workspace resize exposed the guest’s 512 MB per-file limit, which the small verification home had not exercised. Both attempts stopped before replacing the original home. Transfer now uses bounded 8 MB segments with fast gzip, keeping the 512 MB execution file limit intact; tests verify multi-segment round trips, total limits and external-link exclusion.

The populated `pi-viz` home then resized successfully to 1 CPU / 2 GiB in 257.6 seconds. All eight sampled source-file hashes matched after replacement. The original stopped cloud home and private local transfer archive were retained for recovery. Preview reuse now checks the selected source folder before accepting an already-running app, preventing stale previews after a source-sync folder changes.

After the final deployment, both saved apps returned authenticated HTML successfully. Initial opens measured 4.589 and 21.901 seconds; repeated opens measured 0.146–0.362 seconds. Cold-start latency still varies and is not equivalent to warm-preview latency. The resized workstation reopened on its stable editor origin, with Entra sign-in intact.

The chat transition regression was checked in the embedded browser: selecting saved history rendered in 0.85 seconds and returning to New chat rendered in 0.76 seconds in this local run. A fresh no-tool prompt returned `CHAT_LOADING_OK` and appeared in saved history. Keep the embedded client visible while it initializes; hiding it behind readiness state can stall its lifecycle. Browser subscription cancellation must not wait for a background job to end.

The model gateway keeps its upstream HTTP client alive until the last workstation service connection exits. A regression test covers out-of-order workspace shutdown; stopping a warm spare must not break another workspace's inference. Embedded preview servers no longer install process-wide signal handlers over the main broker's handler.

Browser smoke checks after the shared-client fix: Pi, Codex and Claude each returned their requested no-tool sentinel through Ori with Luna selected. Pi's model picker displayed 440 broker-routed entries. These checks establish working panel-to-provider paths; they are not a claim that every catalog model supports every harness protocol. Large-home resize performance was not re-benchmarked in this round.


The direct Learn MCP follow-up passed 299 Python tests, seven polling tests, five chat-transport tests, TypeScript, production build, and architecture report generation. A disposable sandbox initialized Learn MCP, discovered its three tools and performed a search; an unrelated destination returned HTTP 403. The test sandbox was deleted. Existing workstation validation confirmed Claude MCP connectivity, Codex discovery, and Pi executing `lab-learn search` from its browser chat and returning a documentation link. The generated app preview rendered its dashboard. Native Connector Namespace deployment is deferred; authenticated GitHub writes remain an unexecuted example requiring a scoped connection.

The measured workstation resume was 9.8 seconds (1.5 seconds Azure resume, 8.2 seconds bootstrap), not a subsecond editor startup. Operations now loads a separate 343 kB JavaScript chunk (approximately 100 kB gzip) on demand. App preview opening skips editor preference and coding-tool setup, and uses owner-checked local lookup instead of inventorying the group. Copilot review fixes retain issued catalog snapshots for the capability lifetime, preserve the requested warm compute size, continue opening after peer profile capture failure, and document the dictation patch.


The next optimization round reproduced a blank Vite app: HTML arrived but root-relative module assets lost the preview capability. Capability-scoped HTML/JS/CSS asset routing restored visible LUMA and NEXUS rendering without relaxing isolation. A fresh headless sandbox reached readiness in 4.24 seconds and completed file creation/execution in 4.98 seconds (allocation 0.93, bootstrap 2.98).

A synthetic seven-day home archive was uploaded to private Blob, downloaded and hash-verified, and the original sandbox removed. A new environment restored the saved file and returned ARCHIVE_ROUNDTRIP_OK. Archive took 14.05 seconds and restore plus verification command 8.09 seconds for this small test home. Failure tests retain the original sandbox. The initial live attempt correctly refused an external toolchain link; the known image-owned Rust link is now rebuilt while other external links remain blocking. This does not establish large-home archive throughput or full memory snapshot export.

Final automated verification for this round passed 314 Python tests, the polling suite, TypeScript checking, production build and regenerated architecture report. The seven-day archival policy is enabled in private pilot configuration; no private configuration is included in source.

The final browser pass rendered the Supply Chain optimizer, but Solve still failed: its Vite log reported connection refused on local port 8000 after Python package artifact downloads returned 503. This generated app backend remains an outstanding live validation failure; preview-origin regression tests alone do not establish app action readiness.

## Profiling and package protocol follow-up

320 Python tests, polling tests, TypeScript and the production build passed. The complete first/burst/sequential/live profiling results and cost assumptions are in [Performance profile](PERFORMANCE-PROFILE.md). All 32 original execution checks passed, plus six post-optimization quick checks whose cloud deletions completed. Quick results now return after checkpoint durability and before background deletion completes; reservations remain until confirmed cleanup.

The optimizer failure recorded above was infrastructure-related: uv performs HEAD requests for wheel metadata, which the relay denied. Scoped artifact HEAD now returns verified content length without a body, with the existing age/checksum checks. Locked dependencies restored, the unchanged API command restarted, and the browser Solve action produced the shipment plan after refreshing its expired preview lease. No generated MILP solver or frontend code was modified.

Operations now includes a five-minute background ARM inventory, provisioning state, sandbox group defaults/quotas, registry usage, storage settings, local checkpoint/upload limits, package cache, model call count and pending cleanup. The live inventory confirmed three sandbox groups, one Standard Hot LRS storage account, one Basic registry and one managed identity, with no Dynamic Sessions pool or dedicated environment. Cloud observation failures are explicit; cached data is timestamped.

A matched 10 MiB archival test verified identical file hashes: native resume/read 3.464s, archive 20.151s, Blob rebuild/read 7.266s. The policy remains seven inactive days; recommendations are documented without raising the pilot capacity or budget limits.

Chat navigation regression checks include rapid old/new/old selection, waiting for content load after SDK command acknowledgement, and failure recovery. Browser validation must verify the final conversation contents, not only disappearance of the loading overlay. Built-in pool comparisons use `scripts/builtin_session_client.py` with server-owned user/conversation identifiers; credentials stay in the caller.

Pool routing validation covers owner-scoped identities, hourly accounting, capacity rejection before execution, no replay after ambiguous errors, credential-free file payloads, artifact download and durable checkpoint restore. Verify the configured pool with a browser Python request after changing its endpoint.

## Chat availability and parallel command observation

The full chat is an externally loaded iframe. If initial readiness or a thread transition stalls for eight seconds, the app offers a local recovery chat automatically; it never automatically resubmits a message. The recovery view uses the same authenticated `/api/chatkit` protocol, supports saved history and text submissions, and exposes validated artifact downloads. Interactive approval/widget controls remain in the full view; recovery never synthesizes approval actions. A user can explicitly select text view and later retry the full view. Hidden SDK thread-change events cannot overwrite recovery selection, and reconnect clears the old loaded-thread reference. Full-view transitions hide stale controls immediately and fade in loaded content, respecting reduced motion.

Azure command-result polling backs off from 0.4 to 5 seconds. HTTP 429 retries only the result read for the existing command; it does not relaunch it. Failure to remove a completed command's temporary request/result files is logged without discarding its successful result. This was exercised after five parallel agents exceeded the previous constant-rate polling allowance.
