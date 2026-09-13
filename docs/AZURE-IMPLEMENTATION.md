# Production implementation boundaries

The local app is wired to Azure Sandboxes. The remaining production work is identity, a shared durable scheduler, distributed project/file leases, centralized budgets, rate limiting, metrics retention and a highly available authenticated preview broker.

A single local owner and SQLite ledger do not implement 700 concurrent real users. The raised Azure group quotas are a configuration envelope. Verify subscription/region quotas, SDK throttling, admission latency, disk-image readiness and total budget before load testing. Replace local semaphores with a durable queue and owner-scoped leases before scaling multiple broker instances.

Persist project metadata, chat history and artifacts to appropriately scoped shared storage before making the control plane stateless. Retain optimistic concurrency on source manifests and checkpoints. Keep GUI and headless credentials separate and enforce owner authorization at every resource lookup. A shared writable home is not a tenant boundary.

Preserve default-deny egress, package-age controls and tool-service approvals. Authenticate all preview access; the prototype's loopback preview ports are unsuitable as public endpoints. Review any fixed-price infrastructure before provisioning it. Operational budget alerts notify; they do not enforce a cloud spending hard stop.

The current application uses the configuration and lifecycle in [Azure runtime](AZURE-SANDBOX-RUNTIME.md). No production deployment is performed by viewing this document.
