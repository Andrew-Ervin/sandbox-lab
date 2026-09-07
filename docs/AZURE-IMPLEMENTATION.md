# Azure implementation guide

This is a deployment plan for replacing the prototype frontend with an existing enterprise application. It is not a production-ready Terraform deployment. The supplied `infra/lab.yaml` is a **local kind configuration**: do not apply it unchanged to AKS. Local-owner authentication, host port forwards, local-path storage, development images and Coder bootstrap identities must be replaced.

Read [enterprise hardening](ENTERPRISE-HARDENING.md) first. In particular, the current in-workspace Pi capability can be reused by code. If “only the managed coding agent may call an LLM” is mandatory, the separated harness/tool-broker design is a prerequisite to the pilot, not a later optimization.

The native Coder headless trial already separates model inference from generated code; its service identity, APIs and egress still need enterprise integration. The GUI exception remains a separate decision: retain familiar Pi/Ori with monitoring, or accept a separated trusted UI/harness for stronger prevention.

The detailed [managed Pi design and acceptance matrix](MANAGED-PI-DESIGN.md) covers the SDK adapter, credential-free execution environment, developer portal chat transport, browser preview risks and the policy against embedded LLM integrations. It is a proposal, not an enabled deployment profile.

## 1. Decide ownership and access before deploying

Define stable tenant, user, project and conversation IDs. Conversations may have no compute at all; quick files belong to their conversation; persistent projects and developer homes have separate owners and access lists. An app preview grant does not confer workspace administration or permission to publish. Map the current API responsibilities into the existing application's identity and job system; do not carry across localhost bootstrap cookies.

Use Entra sign-in for user-facing APIs and the external Coder developer portal. Validate issuer, tenant, audience, expiry, user status and project grants on every control route, including status, files, previews, run cancellation and capability/approval renewal. Background jobs retain delegated user/project context; they do not become unrestricted service calls. Determine Coder license/organization/RBAC features with the chosen version; the local setup uses two controls because it cannot rely on premium template RBAC.

Start with separate Coder human and AI controls, provisioning identities and execution namespaces. Decide later whether a tested licensed RBAC model justifies consolidating them. Coder's workspace agent handles connectivity. The native Coder headless engine performs inference in its control plane; the alternative Ori/Pi engine runs inside the workspace. GUI workstations currently retain Pi/Ori. Keep these identities and credential boundaries distinct.

## 2. Build images in CI and store them in ACR

Build the quick, AI and developer image families for the selected AKS architecture. Use the pinned, checksum-verified Ori/code-server assets, lockfile installs, reviewed extension assets and base images pinned to multi-platform digests. Retain the reference report as a static artifact, not an execution container. `scripts/download_tools.py` currently downloads host-native assets; an AMD64 CI runner is the straightforward build path for AMD64 AKS.

Example image build shape after the build prerequisites and downloaded assets are ready:

```sh
# Replace REGISTRY with an approved ACR login server. Use CI workload federation.
docker build --target quick -f sandbox/Dockerfile -t REGISTRY/sandbox/quick:RELEASE .
docker build --target ai -f sandbox/Dockerfile -t REGISTRY/sandbox/ai:RELEASE .
docker build --target developer -f sandbox/Dockerfile -t REGISTRY/sandbox/developer:RELEASE .
# Scan, produce SBOMs, sign, then publish and deploy by digest through reviewed CI.
```

These examples show the image pipeline, not the remote-harness implementation. Create a separate trusted harness image when that broker is implemented; it must not execute repository code or install project packages. Admission should reject unsigned/unapproved images, mutable production tags, privileged pods, host mounts and policy-breaking specs. Upgrade SDKs through reviewed image releases; projects do not receive root/sudo.

Bootstrap/image builds are a trusted supply-chain path and currently fetch public dependencies. Apply organization provenance, vulnerability/license scanning and release-age policy in CI too; the runtime gateway's five-day rule does not automatically secure the image build.

## 3. Provision AKS trust zones

Use a supported AKS version and a CNI/network-policy combination validated with your actual cluster and pod addressing mode. Create a private control plane where appropriate. Use a system pool for cluster services, a trusted service pool for APIs/controllers/gateways/harnesses, and separate tainted user pools for quick compute, AI projects and human workspaces. Restrict tolerations/node selection through admission so user-controlled templates cannot schedule into trusted pools.

Enforce Restricted Pod Security, non-root, seccomp, capability dropping, no host networking/PID/IPC, no hostPath/socket, no execution service-account tokens, bounded PIDs, and CPU/memory/ephemeral-storage/PVC quotas. Namespaces are not VM boundaries. Validate the supported runtime/node isolation against hostile code; do not assume installing Firecracker changes AKS isolation.

Use default-deny ingress/egress in every zone, including trusted services with narrowly defined routes. In the separated harness design:

| Source | Allowed destinations |
|---|---|
| Quick code | No network; broker transfers selected inputs/outputs |
| AI code / human IDE | Required Coder control channel, internal package mirror, narrowly scoped execution broker channel if needed; **no model gateway, managed Pi/turn API, enterprise DB, Graph or Azure metadata access** |
| Managed Pi harness | Model gateway, execution tool broker, approved MCP broker |
| Model gateway | Only approved OpenRouter endpoints through controlled egress; no general proxy |
| MCP broker | Approved destination services using dedicated authorization/identity |
| Storage broker | Owner-scoped storage and required metadata services |
| Preview gateway | Only authorized app targets; strip credentials and isolate active content |

The local model/package gateways use separate domain-restricted CONNECT proxies in addition to application validation. Coder control planes still have broader public HTTPS for provisioning and native inference. Replace these with organization-controlled egress/mirrors and test IPv6 too. Internal DNS must not forward attacker-controlled external queries. Verify private endpoints, node/metadata access, tunneling through approved channels and Coder port-forward capabilities, not just HTTP allowlists. Enforce approved package age from trusted metadata, and exact expiring overrides through a separate human role. Never forward arbitrary unknown package names to public registries in a strict data-egress deployment.

## 4. Centralize credentials and policy

Enable AKS OIDC issuer and Workload Identity. Give narrowly scoped federated identities to trusted controllers, model/enterprise/storage brokers and CI; **none to generated-code pods**. Store long-lived provider secrets in Key Vault and inject/retrieve them only into trusted services. Do not expose a shared OpenRouter capability to the IDE when the separated model-access requirement applies. [AKS Workload Identity](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview).

Keep enforced `provider.zdr=true` / `data_collection=deny` and model/provider allow policies centrally. Validate ZDR eligibility and contract/region/data-class requirements. Set account-level controls too, and disable optional prompt logging. Exa is a separate disclosure path: preserve only where the project classification permits it. Do not treat ZDR as DLP. Add payload minimization/redaction, secret detection and a reviewed export workflow for regulated data.

Use your existing OPA-backed MCP controls as the final enforcement point. A trusted broker resolves Entra subject/project entitlements, selects cataloged operations and requests decisions. Validate downstream OAuth audiences; do not relay bearer tokens indiscriminately. Implement exact-operation approval records, independent reviewers, resource-version checks, atomic nonce consumption, transaction/row limits and idempotent commits. The supplied [OPA example](../infra/policy/README.md) is a contract/test starter only. API Center can supply the approved catalog; authorization happens in the broker and destination service.

## 5. Replace local persistence and in-process jobs

Move conversation/project/job metadata to managed PostgreSQL with tested tenant/project authorization and backup/restore. Use a durable queue such as Service Bus for accepted turns; workers lease jobs with fencing/heartbeat and idempotency. Do not store critical running state only in web-worker memory or SQLite. A browser disconnect detaches the viewer; a worker restart is reconciled without replaying destructive operations automatically.

Use Blob for immutable source checkpoints, selected inputs and artifacts, with encrypted transport, private endpoints, project ownership, retention/versioning and soft delete as required. Only a trusted broker can upload/delete retained snapshots; the code pod must not delete its recovery history. PVCs remain active Linux working volumes for compilation and package installs. Use Azure Disk for private working trees where attach/topology behavior is suitable; evaluate Azure Files only for genuine shared-filesystem needs. Exclude `.venv`, node_modules, transient caches and credentials from source checkpoints; retain lockfiles and image/ABI metadata.

The current user choice is **local persistence for the prototype**; no Azure adapter is enabled. OneDrive can be an optional Graph checkpoint/import/export service, not a mounted home. Use an explicit app-folder/consent model, change tracking, ETags, single-writer leases and acknowledged revision manifests. Users can delete OneDrive data, so it is not an immutable safety backup. OneLake is a candidate for governed analytical datasets, with its own permissions/API behavior. See [architecture storage options](ARCHITECTURE-GUIDE.md).

## 6. Separate development preview from published application hosting

Today an app server shares the Coder workspace that built it. Clicking its app card resumes that workspace and replays its stored launch recipe; idle workspace shutdown stops the server. Closing chat is unrelated. Static reports/HTML need only an artifact preview listener, not a coding pod.

For enterprise use, keep that preview flow for iteration, but add an explicit **publish** workflow: validate source, scan dependencies, build a clean immutable runtime image, assign an application identity with reviewed privileges, and deploy to separate app-hosting capacity. Running an app must not require the developer's home, Pi model access or an open chat. Apply independent health checks, retention, authentication, budgets and idle policy. A preview must never silently become a production service with the builder's identity.

Developer workspaces may be entered directly via the Coder portal/VS Code. SSO, lifecycle, managed chat transport and authorization must work there without depending on the main chat application's localhost session. Keep IDE origin separate from app/HTML preview origins. Use authenticated routing and expiring owner-scoped grants for previews; support WebSocket/OAuth only with explicitly designed isolation, not by removing sandbox restrictions globally.

Do not store a managed-Pi bearer token in the workspace-side extension host: it can be repurposed just like a model token. Put the managed chat pane in the trusted portal shell and keep its credentials outside the IDE. Generated browser JavaScript is outside AKS egress policy; isolate origins and control APIs, and select remote browser rendering or validated enterprise browser controls if all external preview egress must be prevented.

Enforce the no-LLM-integration policy in the trusted authoring configuration and mandatory export/publish review. Check the complete source/build artifact, including manual edits and shell-generated files. Bind approvals to immutable source/image digests and fail closed on missing checks. Scanning can flag integrations; only credential/network boundaries prevent execution code from spending the platform's model allowance.

## 7. Warm capacity, scale-up and scale-to-zero

Separate four controls: durable job workers, ready unused sandbox reserve, running/persistent workspace leases, and node pools. KEDA can scale workers from queue demand; a pool controller must turn that demand into schedulable pods for Cluster Autoscaler to see it. KEDA scaling a deployment is not a substitute for atomically claiming a clean per-session pod.

Size clean reserve from measured arrival rate × tail readiness/refill time + burst allowance, capped by tenant/global budget. Include image pull, node provisioning and volume attach in readiness. Prewarm before predictable weekday ramps, release scheduled floors afterward, and retain reactive wakeup overnight/weekends. Measure p50/p95/p99 queue wait, ready-pod age, admission refusals, execution duration, memory/CPU and startup phase times. Weekly user count or minute-average execution count alone cannot size the system.

Start with local idle behavior as a pilot policy: quick reserve expires after five minutes, used quick pods are destroyed, AI projects stop after five idle minutes, developers after ten, preview leases after two. Active job/IDE interaction leases prevent shutdown; status polling does not. Checkpoint before releasing project compute and retain files separately. Any failed sync must be visible and must not be reported as saved. At scale, use durable compare-and-swap leases and a single controller leader/fencing to prevent double assignment or stopping active work.

User node pools may autoscale to zero; AKS system capacity and trusted availability services do not. Configure finite max nodes, subscription/vCPU quota, pod/IP capacity, per-namespace budgets and graceful overload behavior. “Scale as needed” means up to approved capacity, with a queue and an operator alert at the limit. Storage remains billable after compute stops. [AKS cluster autoscaler](https://learn.microsoft.com/en-us/azure/aks/cluster-autoscaler-overview), [system node pools](https://learn.microsoft.com/en-us/azure/aks/use-system-pools).

See [AKS-DRAFT.md](AKS-DRAFT.md) and `infra/aks/` for the existing illustrative pool/KEDA policies. They need site-specific resources, identities, metrics and quotas before application; they are not an unattended production rollout.

## 8. Release gates and operational handoff

1. **Identity/isolation:** cross-user conversation/files/preview/workspace access denied; direct code → model/MCP/DB/metadata denied; no token reuse from code; threat-model Coder channels and package hooks.
2. **Authorization:** OPA outage/stale policy deny; forged/expired/changed/replayed/self-approved operations deny; concurrent approval consumption tested; privileged destination also enforces limits.
3. **Data:** approved model/search routing verified, DLP/retention classification documented, logs redacted, per-project storage restore tested after deletion or pod loss.
4. **Lifecycle/load:** cold-zero wake, scheduled ramp, bursts, queue overload, node loss, interrupted workers and scale-down with active previews; no tenant receives a previously used warm filesystem.
5. **Supply chain:** reproducible builds, SBOM/signature verification, package-age policy including transitive dependencies, expiring exceptions and reviewed image updates.
6. **Operations:** security owner, on-call, kill switches, spending alerts, retained audit decisions, policy rollout/rollback, revocation and incident containment runbooks.

Run a business-user pilot with synthetic/approved data and read-only tools before expanding to IT workflows or production writes. Reuse the existing frontend, but preserve these server-side boundaries and the separate lifecycles underneath it.

## Bounded storage and supply-chain follow-up

Local kind uses local-path storage, which currently has no online expansion support. Do not merely set allowVolumeExpansion on this driver or claim its requested PVC size is a hard filesystem quota. Monitor the host disk too.

For AKS, choose a CSI StorageClass supporting expansion. Proposed policy: start project volumes at 10 GiB; at 80% usage for five minutes, grow to the next tier (20/40/80 GiB), subject to per-user and namespace storage budgets. Cap automatic growth at 80 GiB, rate-limit changes to once daily, alert at the cap, and require an administrator for larger allocations. Kubernetes cannot shrink volumes in place. Keep the desired size in the Coder provisioning configuration so subsequent builds do not try to undo a resize. Implement and test this controller before advertising automatic expansion. Scratch-space changes require a workspace restart; never delete project files automatically to reclaim capacity.

Do not enable unbounded snapshots. Proposed retention: snapshot only changed active projects, retain seven daily plus four weekly restore points, and expire deleted-workspace recovery copies after seven days. Enforce both count and billed-byte budgets; tag snapshots by owner/project/expiry, reconcile orphaned snapshots, and alert on cleanup failures. A budget failure should stop new snapshots and alert, not silently destroy the only valid recovery point. Exclude rebuildable package caches by separating them from source/data volumes. Backup Coder databases consistently and exercise restores. These are proposed production controls, not an enabled snapshot service.

Deferred supply chain: integrate the enterprise Snyk organization with GitHub PR checks for dependencies, containers and IaC; enable secret scanning, protected branches and required review. Build trusted images through GitHub Actions with Azure workload identity/OIDC, publish to ACR, and deploy reviewed immutable digests. Keep conversations, uploads, workspace volumes and credentials out of Git. No Snyk integration is installed by this prototype.

Storage expansion reference: https://kubernetes.io/docs/concepts/storage/persistent-volumes/#expanding-persistent-volumes-claims
Destination ACL reference: https://www.squid-cache.org/Doc/config/acl/

### Durable project deletion worker

The local prototype now persists confirmed deletions and processes them independently of browser requests, with two concurrent operations and bounded retry backoff. Before scaling the application to multiple AKS replicas, move this operation ledger from local SQLite to the shared application database/queue and claim each operation using a lease. Run one logical worker per project so two replicas cannot submit competing Coder builds. Keep API requests short, expose operation progress, and acknowledge completion only after workspace storage and application-owned files are removed. Do not scale local SQLite workers across replicas by sharing the database file.

### Project-linked developer and chat environments

Retain distinct developer and headless workspace IDs, namespaces, identities and home storage. A link is organizational, not permission to execute chat code in the developer workstation. The local prototype supports explicit source snapshots in either direction, reviewed by the user and published into a new import folder; merging into live source is deliberate. Installed packages, credentials and processes do not move with that copy.

For AKS, replace the two in-memory, five-minute local reviews with owner-bound records and immutable staged objects in shared storage. Bind approval to project, source/target workspace, direction and content hashes. Enforce Entra membership and tool/transfer policy server-side; audit approve/apply events and apply secret scanning/DLP before promotion. Do not trust client flags or a chat approval widget alone. Apply byte/file limits and a lifecycle policy to abandoned review objects and imports, with recovery grace for failed transfers. Use distributed project leases instead of process-local locks, and do not apply local-owner auto-migration to a multi-tenant installation.
