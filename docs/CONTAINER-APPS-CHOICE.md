# Sandboxes versus regular Container Apps

Regular Container Apps is a good fit for the trusted web application, broker and
stateless APIs. Sandboxes is a good fit for isolated user code, interactive
workspaces and process state that should survive suspension. Neither service
automatically implements our user ownership, file sync, budgets or approval flow.

| Requirement | Sandboxes | Regular Container Apps |
|---|---|---|
| Run arbitrary user code | Per-sandbox microVM boundary, exec/files/lifecycle data plane | Need a session execution API and isolated allocation strategy; sharing a replica is not per-user isolation |
| Sleep and resume an editor | Memory/disk suspension and snapshots | Scale-to-zero replaces replicas; restore files and restart processes from external state |
| Route to a specific workspace | Addressable sandbox and exposed ports | Need durable session routing, leases and recovery; load-balanced replicas are interchangeable by design |
| Control outbound requests | Built-in host/path/method rules and secret/identity injection | VNet routing plus a firewall/proxy or application broker for comparable policy |
| Connect MCP tools | Native connector attachment or narrow direct egress | Standard MCP clients work; managed credential/tool policy integration remains application work |
| HTTP/queue autoscaling | Application chooses and tracks individual allocations | Declarative scaling rules, revisions and traffic management |
| Larger CPU/RAM and GPUs | Current documented tiers top out at 4 CPU / 8 GiB; do not assume GPU support | Wider Dedicated/GPU choices, with region/quota and pricing constraints |
| Image versus size | Same image can run in different supported tiers | Same image can run at different resource settings; resizing creates a revision/restart |

The higher ACA ceiling is real, but ordinary **Consumption CPU** also tops out at
4 vCPU / 8 GiB per replica. The larger figures often refer to Dedicated profile
nodes, shared by apps, with some capacity reserved for the platform. Current
profiles include D32 (32 CPU / 128 GiB) and E32 (32 CPU / 256 GiB), and GPU profiles.
Flex offers more memory flexibility but currently cannot scale to zero. Dedicated
and GPU plans are not silently interchangeable with a small consumption sandbox
in the pilot budget.

## Recommended direction

Keep Sandboxes for short Python, headless projects and interactive workstations.
Use regular ACA for a future hosted trusted broker/frontend and for published
stateless apps with sustained multi-user HTTP traffic. Keep a development preview
in its owning workspace so edits appear immediately without a separate build and
deployment. A published app can later become a regular ACA revision without
moving the developer's entire home into that service.

For fastest interactive starts at low cost, retain the ten-minute idle window and
one clean spare per recently used role. Preinstall stable runtimes and tools in
the image; do not rebuild an image for each size. Suspend stateful workspaces
between visits. Measure end-to-end editor, broker and preview readiness separately
from Azure allocation time. Our startup still includes broker connection, settings
and application readiness work; sub-second platform startup does not promise a
sub-second complete editor.

For very short Python bursts, pool clean isolated sandboxes and reuse them only
after reset. Do not pack unrelated users' arbitrary code into one shared process
to improve occupancy. A regular ACA API can handle many requests per replica,
but that concurrency is not a ready-made secure code-execution pool.

No service switch, Dedicated node, GPU, Firewall, or APIM resource was provisioned
for this comparison. Those changes need a measured workload and a new cost review.

## Loading changes in this round

Operations charts and resource controls load on demand. The Operations chunk is
about 343 kB uncompressed / 100 kB gzip in the measured build, separate from the
initial chat page. A known workspace opens through an owner-checked local lookup
instead of fetching the entire Azure group first. App preview startup skips
editor profile synchronization and coding-harness configuration; editor opens
retain those operations. Existing ready previews still use the health-checked
reuse path. CPU/memory allocation and warm-pool limits were not increased.

References: [Sandbox lifecycle and isolation](https://sandboxes.azure.com/docs/sandboxes/),
[ACA workload profiles](https://learn.microsoft.com/en-us/azure/container-apps/workload-profiles-overview),
[ACA scaling](https://learn.microsoft.com/en-us/azure/container-apps/scale-app),
[Sandbox egress](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-egress-policies),
[ACA firewall architecture](https://learn.microsoft.com/en-us/azure/container-apps/use-azure-firewall).
