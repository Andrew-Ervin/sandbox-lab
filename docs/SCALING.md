# Azure sandbox scaling

The unit of allocation is an isolated sandbox, not a chat and not a separately deployed Container App. A headless project reuses one sandbox across its conversations. One run at a time edits a project's files. A linked GUI workstation has a separate home and sandbox. An app server shares its owner's sandbox; opening a preview does not create a separate app resource.

## Current pilot configuration

| Role | CPU / memory | Running admission ceiling | Retained group quota | Idle | Hard lease |
|---|---|---:|---:|---:|---:|
| Python | 1 / 2 GiB | 500 | 501 | 10 min | 10 min |
| Headless | 2 / 4 GiB | 100 | 1,000 | 10 min | 60 min |
| Developer | 2 / 4 GiB default; 1 / 2 or 4 / 8 optional | 100 | 1,000 | 10 min | 60 min |

The existing Azure group quotas have been increased without allocating capacity. These are ceilings, not a promise that all can run simultaneously in this subscription. A **$12/hour aggregate compute admission guard** takes precedence during testing; additional work waits. There is no logical chat count cap. The broker permits 128 concurrent jobs and queues up to 512 additional jobs; further work receives explicit backpressure before it allocates retained stream state. Thirty-two command transfers and eight SDK workers bound local pressure. Project locks serialize changes to a shared home. The cumulative $200 test allowance uses a conservative $150 operational cutoff plus reserve for delayed billing and other costs. Do not remove these guards to demonstrate scale.

## Warm capacity and stop policy

Actual execution or opening a workspace renews that role's ten-minute demand window. The broker maintains at most one clean, never-assigned spare per recently used role. A new project or Python call can claim it atomically; the controller replenishes the spare. Existing projects resume their own disks. A used home is never reassigned to another project. Quick calls checkpoint files and delete their sandbox when finished.

User activity and active commands protect work from the idle reaper. Read-only polling and background source sync do not refresh user activity. A visible preview lease protects its workspace. Explicit Stop all cancels waiting admissions, pauses the warm controller, checkpoints eligible source and stops compute. Closing a preview stops renewal; the runtime remains warm until idle expiry. A 60-minute persistent-compute lease is a testing safety deadline even if a session remains open; reopening reserves another bounded lease. This is separate from the ten-minute idle policy.

The Azure service auto-suspend is also configured for 600 seconds. Its definition of activity includes incoming traffic, shells and file operations. The application's user-activity reaper is needed because background service connections and checkpoints can otherwise keep a sandbox active. If the local controller is abruptly lost, lease enforcement by the relay and Azure auto-suspend provide bounded fallback behavior; cleanup cannot be guaranteed through a cloud outage.

## Cost model

Active compute estimates in East US 2 are $0.108/hour for Python, $0.216/hour for headless, and $0.108 / $0.216 / $0.432 per hour for light / balanced / performance workstations. One default spare of each role costs $0.54/hour, or $0.09 for a full ten-minute warm tail. Existing workstations retain their previous size. A 30-second Python allocation is $0.0009 before startup/cleanup and other charges.

The requested 100 headless + 100 developer + 500 Python simultaneously at the balanced workstation default would consume 900 vCPU and 1,800 GiB, estimated **$97.20/hour** ($8.10 for five minutes). With all workstations at performance size this becomes 1,100 vCPU / 2,200 GiB and $118.80/hour ($9.90 for five minutes). The $12/hour testing guard deliberately queues most of that demand. To serve the entire peak without waiting requires a separate budget, quota verification and distributed load validation.

Resource sharing across unrelated users would weaken isolation: each active independent execution context needs its own isolation boundary. Efficient pooling here means reusing the same project's home, sharing its app processes, reusing clean service capacity, immediate Python cleanup and suspension between tasks. It does not mean placing unrelated tenant code in one writable home.

## Dynamic Sessions comparison

Sandboxes provide direct lifecycle, disk images, snapshots, files, ports and egress control. Dynamic Sessions provide a managed session-ID router, pool allocation, ready instances and cooldown/TTL cleanup. Their session state is ephemeral. Storage is one difference; managed request routing and lifecycle are also significant.

The custom Python Session Pool experiment used a dedicated E16 profile with a roughly $1.650416/hour one-node floor. A nominal 1 CPU / 2 GiB custom session can share that node with other isolated sessions subject to actual packing and service overhead. Sixteen slots is an optimistic CPU-only bound, not a verified packing guarantee. The equivalent sixteen Sandbox allocations cost $1.728/hour; one Sandbox costs $0.108/hour. At low occupancy Sandboxes are much cheaper. The experiment's pool and its managed environments were removed after testing. Built-in interpreter pools have a different active-session billing model: the current retail meter is $0.03 per allocated session-hour, billed in one-hour increments. Five hundred distinct 30-second allocations therefore start at $15, while 500 Sandbox allocations occupying 1 CPU / 2 GiB for exactly 30 seconds total $0.45 before overhead. Reusing one interpreter session within its billed hour changes that comparison; a continuously occupied built-in session can be cheaper. Do not substitute that price for custom-container pools.

Supported Sandbox tiers are 0.25/0.5, 0.5/1, 1/2, 2/4 and 4/8 CPU/GiB. The workspace capacity selector supports 1/2, 2/4 and 4/8. Azure snapshots cannot change CPU/memory on restore. Resizing therefore saves a bounded private home archive in 8 MB segments, stops the old sandbox, creates a new one at the selected tier and restores files as the unprivileged user. The workspace ID and project association remain stable. Save editor buffers first; processes and terminals restart. Archives over 4 GB uncompressed or 2 GB compressed are refused before replacement. The old stopped home and private local archive remain recoverable and may incur storage costs; cleanup is explicit. There is no live vertical autoscaling. The current sandbox and Session Pool paths have no configured GPU. Ordinary Container Apps/Jobs have separate GPU options with regional and quota constraints; adopting one is a separate deployment, not a checkbox on this sandbox group.

Sources: [Sandboxes overview](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-overview), [custom sessions](https://learn.microsoft.com/en-us/azure/container-apps/sessions-custom-container), [Container Apps billing](https://learn.microsoft.com/en-us/azure/container-apps/billing). Prices are planning estimates, exclude taxes and other meters, and must be refreshed before changing compute profiles.

Preview opens probe an already-running app before invoking its startup recipe. Each preview keeps a bounded connection pool to its fixed sandbox tunnel, rejecting upstream cookies. Warm reconciliation runs independently for each role so a capacity wait cannot stall another role’s cleanup. A developer standby follows the most recently requested workspace tier. A standby in a different tier is retired before allocation, so it cannot keep incurring cost while the requested light, balanced, or performance workspace starts.

The editor listener lease is ten minutes. Direct-editor user input renews it; unused open tabs do not create an endless keepalive. This is separate from short app/artifact preview leases.

The transfer is segmented so large installed-tool homes do not exceed the guest’s unchanged 512 MB per-file limit. Aggregate transfer limits remain enforced. In-progress resize counts as busy and is excluded from idle reaping; operational lease/budget limits still apply.
