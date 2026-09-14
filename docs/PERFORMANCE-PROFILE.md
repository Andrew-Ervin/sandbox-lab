# Execution profiling and retention economics

Measured September 13, 2026 on the existing Azure pilot. This is a small functional benchmark, not a load-test SLA. Private receipts remain outside source.

## Workload and method

Both paths compute the sum of squares for integers 0 through 9,999 with Polars, write a JSON artifact, and verify 333283335000. Headless includes the configured Luna agent's planning, one real shell command, final answer and artifact collection. Quick Python executes supplied code without model inference. Both use their normal adapters and saved-state path.

Clean-spare claims were disabled in the benchmark process to measure genuinely new allocation without taking the live broker's reserved workspace. First run, five concurrent new allocations, five sequential new allocations, then five sequential calls on the same live sandbox were measured. The five concurrent requests were dispatched together, before any completed. Test-owned sandboxes were deleted.

Quick Python normally deletes each sandbox after saving its checkpoint. Its same-live row is an experimental reuse measurement using the same adapter, not a feature deployed for users. It still starts a fresh Python interpreter. No unrelated user shares that test sandbox.

| Path and phase | Per-request seconds | Median |
|---|---|---:|
| Quick, first new | 10.545 | 10.545 |
| Quick, five concurrent new | 9.402, 10.363, 10.848, 11.029, 11.167 | 10.848 |
| Quick, five sequential new | 9.860, 9.781, 9.472, 9.697, 9.769 | 9.769 |
| Quick, same live (experimental) | 1.186, 1.149, 1.128, 1.161, 1.143 | 1.149 |
| Headless, first new | 9.711 | 9.711 |
| Headless, five concurrent new | 9.371, 9.624, 9.766, 10.188, 10.298 | 9.766 |
| Headless, five sequential new | 9.664, 11.447, 9.138, 10.420, 9.782 | 9.782 |
| Headless, same live | 5.648, 4.972, 6.357, 4.334, 4.654 | 4.972 |

After deferred cleanup was implemented, a fresh quick call returned in **3.601s**; five overlapping fresh calls returned in **3.607, 3.661, 3.670, 4.203, 4.252s** (median **3.670s**). All six cloud deletions were verified complete afterward.

The original quick roundtrip included waiting for deletion; headless retained its workspace for follow-ups. A stage probe attributed 1.746s to creation, 1.164s to execution, 0.069s to checkpoint processing, and 6.620s to deletion (10.371s total). The implemented improvement returns after checkpoint success and durably queues immediate deletion, retaining the reservation and retrying failures. It does not pool used workspaces or extend their idle lifetime. Operations exposes pending cleanup and completion/failure events.

The isolated profiling window increased the local cumulative usage/reservation ledger by about $0.113. This is not an Azure invoice or an isolated bill for every concurrent activity. Microsoft billing remains delayed.

## Archive economics

Stopped sandboxes already release CPU and memory. Moving a saved home into Blob targets retained-state footprint, not days of compute. The documented API does not expose export of a native full snapshot into customer Blob. Native memory resume preserves more state; home archives require reconstruction and lose processes/scratch outside the saved home.

At 10 new sandboxes/hour, arrivals are 240/day: 228 one-time, 9.6 one-day, and 2.4 multi-day/week. Assuming the first 99% reach their final use and the arrival rate is steady, the inactive pre-archive population is approximately:

| Inactivity delay | Completed short-use sandboxes awaiting archive | Reduction from 7 days |
|---|---:|---:|
| 7 days | 1,663.2 | — |
| 2 days | 475.2 | 71.4% |
| 1 day | 237.6 | 85.7% |

A single 1,000-sandbox group could not hold the seven-day short-use backlog if all arrivals use that group; actual distribution across roles matters.

This excludes the active one-day cohort and the 1% long-lived cohort, whose duration and revisit distribution were not specified. The percentages do not predict how often a user returns after a given inactivity gap.

A sandbox retained-state storage rate could not be verified in the current public retail meters. Do not substitute the similarly named GitHub Compute Sandbox Memory Storage meter or registry storage pricing. Let S be native retained GB per sandbox, B the actual Blob GB per archive, Ps the native monthly $/GB rate and Pb the Blob monthly rate. At steady state, shortening delay by d days saves approximately `237.6 × d × (S × Ps − B × Pb)` per month, before transfer/operations and differing version histories. An illustrative S=1 GB, Ps=$0.05, B=0.1333 GB, Pb=$0.0184 gives about $67.78/month for 7→1 days, $56.49 for 7→2, and $11.30 for 2→1. **The native rate and size in this illustration are assumptions, not Azure quotes.** If native storage is uncharged during preview, archiving can instead add cost.

Current East US 2 retail meters: active CPU $0.000024/vCPU-second, memory $0.000003/GiB-second; General Block Blob v2 Hot LRS $0.0184/GB-month at the first tier. A 1 CPU/2 GiB allocation is $0.108/hour before grants; 2 CPU/4 GiB is $0.216/hour. An unnecessary ten-minute running tail on every arrival would cost approximately $129.60 or $259.20 per 30-day month respectively. This is a different and often larger lever than the archive delay.

Archives currently use base64 JSON chunks, about 33% overhead before small manifest costs. At 100 MB compressed per home, 7,128 short-use arrivals/month add about 950 GB of Blob payload, increasing the eventual monthly storage run rate by about $17.49 for each month's retained cohort. At 5 MB, that increment is about $0.87; at 500 MB, about $87.44. These exclude transactions, versions, data transfer and active/archive work. No archive expiry has been enabled, so retained data grows over time.

The pilot's 1 GB total, 100-object and 2 GB/week upload caps are deliberately far below that workload. They fail closed and retain originals. Production archival needs appropriately budgeted capacity, a binary/content-addressed store, and an explicit retention/deletion policy. Do not raise the pilot limits implicitly.

## Resume latency and next choices

A matched test with a 10 MiB incompressible file took **3.464s** for native resume plus checksum read and **7.266s** for Blob reconstruction plus checksum read: **3.802s additional latency**. Archiving took **20.151s**, outside the reopen path. Both reads matched the original checksum and test compute was deleted. This is one sample.

The earlier small-home Blob restore completed a fresh rebuild plus file read in 8.09s. That is not an editor/app readiness benchmark and does not predict a large dependency-heavy home. Previous populated-home transfer took minutes. Archive timing depends mainly on size and restored processes; choosing one versus two days changes the frequency of restores, not the cost of an individual restore.

Recommended evaluation: start with 48 hours for persistent developer workspaces, consider 24 hours for completed one-time headless work, and keep actively revisited work native. Keep the existing seven-day pilot policy until the retained-state rate and actual archive sizes/revisit intervals support the switch. Quick Python already deletes after checkpointing, so this policy does not save its retained-sandbox cost.

Further options, not silently deployed:

- One short-lived live Python sandbox per chat can approach the experimental ~1.15s path; it needs per-chat serialization, expiry, restart recovery and stronger cleanup accounting. Keep isolation between unrelated users.
- A preinstalled authenticated execution daemon could remove repeated SDK polling/cleanup calls. This changes the trusted command transport and needs a security review and reconnect/idempotency design.
- A clean memory snapshot after trusted bootstrap may reduce headless setup further; credential rotation and a supported warm-resume check remain mandatory.
- Run the broker near Azure to reduce control-plane roundtrips. A regular Container App for the broker changes hosting/auth/storage and may add always-warm costs.
- More clean spares help bursts only if demand is predictable. Each additional 1 CPU/2 GiB spare costs up to $0.018 for a ten-minute warm window; 2 CPU/4 GiB is $0.036, before grants.
- Memory suspend helps expensive editor/app process startup. Blob mounts are useful for large shared artifacts; keeping dependency trees and build I/O on local disk avoids object-storage filesystem penalties.

Sources: [Sandbox state and snapshots](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-snapshots-state-management), [sandbox overview](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-overview), [Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/), [Blob pricing](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/), [Microsoft Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).
