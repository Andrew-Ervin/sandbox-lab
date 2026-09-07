# Sandbox Lab trust boundaries

This is a single-owner security experiment on one local machine, not a hardened multi-tenant AKS service. The host, Docker Linux VM, Kubernetes node, chat backend, both Coder control planes, their databases, model gateway, and package proxy are trusted. Code, project dependencies, generated pages, attachments and model output are untrusted.

## Execution separation

| Boundary | Enforcement |
|---|---|
| Human vs AI | Independent Coder instances, databases, accounts and template catalogs. Each provisioner can create pods/PVCs only in its own execution namespace. |
| Quick execution | Each warm pod is used once and deleted. No network policy permits quick-pod egress. No project volume, model key, Kubernetes token or host filesystem is mounted. |
| Persistent AI | Coder owns the workspace and its project PVC. With `coder-native`, inference runs in the Coder control plane and code has no model route/capability. With the source default `ori-pi`, Pi runs in the pod with an expiring gateway capability. |
| Host access | Restricted Pod Security admission, UID 1000, all capabilities dropped, no privilege escalation, read-only root filesystem, RuntimeDefault seccomp, no host mounts, Docker socket or host namespaces. |
| Resource use | Pod CPU/memory/storage limits, namespace quotas and a kubelet PID limit of 128. Quick Python has a 30-second wall timeout; persistent chat turns have a ten-minute backend limit. |
| Credentials | OpenRouter key remains in trusted backend/control-plane configuration. Chat uses a non-admin Coder service account with the organization `agents-access` role. Workspace agent tokens are still credentials and are present in their own pods. |

The model's routing decision and instructions are **not** security controls. Generated Python executes inside the pod, never in the FastAPI process or directly on macOS. Python's subprocess supervisor is not itself an isolation boundary; the disposable pod and its enforced policy are the boundary.

## Network and browser exposure

Persistent workspaces can reach their own Coder control, internal-only DNS and a read-only package facade. GUI and Ori/Pi headless workspaces additionally reach the model gateway; native Coder headless workspaces cannot. External DNS, direct internet connections, arbitrary CONNECT tunnels and package publishing/uploads are blocked. The package service accepts all valid registry package names and their dependencies, applies a five-day age gate, and checks available artifact hashes. Go/Julia use first-observed quarantine. Explicit, expiring human exceptions are managed from Network & packages; coding tools cannot approve themselves. Existing installed packages remain usable. See [package policy](PACKAGES.md).

Exa web search is permitted through OpenRouter's server tool on the model route. Model/search payloads are approved outbound paths and still need governance; the prototype is not a DLP system. The optional private mock-email MCP experiment is enabled only on the original lab and is excluded from source; clean installs disable it. General enterprise MCP connectivity and additional use-case allowlists remain future work. Local Calico policy uses a dedicated internal resolver; AKS must validate equivalent enforcement and use a trusted MCP broker.

Local chat and Coder ports bind to 127.0.0.1. Chat requests validate Host/Origin, use an HttpOnly SameSite cookie and require a CSRF header for mutations. The bootstrap authenticates a local owner, not an individual person. Any process already running as this host user is trusted and can access the lab.

Generated HTML and app previews use separate loopback ports with a CSP sandbox that omits `allow-same-origin`. Preview proxies strip cookies, Authorization and upstream Set-Cookie, reject redirects and bound response size. Active artifacts are never rendered on the trusted chat origin. Download endpoints require session ownership and return attachment responses. Artifacts are regular files only, without symlinks/FIFOs, up to 8 MB each and 16 MB total per run. Generated preview code still deserves review; it is not trusted application UI.

Isolated preview servers and port forwards expire after two minutes without a renewed lease, or a backend restart. Authenticated links in the run panel create a fresh preview server when reopened. Clicking an app resumes its owned workspace and replays a confined launch recipe without messaging chat. A static artifact needs no workspace. App previews support HTTP, not WebSockets/HMR, cookies or OAuth. Ask for a production/static build when a framework's development preview requires those features. General dataset upload, streamed model tokens, multi-user sign-in and crash-resumable jobs remain future work. Projects, files, linked developer workstations and automatic source sync with conflict handling is implemented.

## Remaining production work

- All AI chats currently share one local owner's Coder identity. Separate pod filesystems do not make different chats independently authorized tenants. Before adding users, map each user/project to appropriately scoped Coder identities and verify Coder tools cannot select another project's workspace.
- Kubernetes containers on this single node share the Linux kernel. Separate namespaces are not VM isolation. Before treating arbitrary hostile code as production workloads, evaluate a supported sandbox runtime (for example gVisor/Kata where available), dedicated node pools or separate clusters, and test the exact AKS runtime.
- Replace loopback sessions with SSO and authorization, TLS, dedicated preview origins, durable ownership-scoped artifact storage, encrypted secret management and short-lived credentials. Add persistent quotas/rate limits, workload cleanup, audit logging and incident response.
- Pi/Ori receives a model-scoped, expiring bearer credential: one hour for humans and eleven minutes for an Ori/Pi headless turn. There is no request-count allowance or exhaustion ledger. Existing signed credentials with legacy count fields are accepted until expiry, with counts ignored. GUI code can access and reuse its own credential; this is not a Pi-only execution boundary. Native Coder execution pods receive no model credential.
- The local broker token is valid for 24 hours. Renew it with `scripts/broker_credentials.py`; refresh Coder login sessions with `scripts/configure_agents.py`. Do not give model-executed code the administrator kubeconfig or Coder admin tokens. The existing trusted host control process uses the local admin connection for workspace setup and read-only live status; replace this with scoped operators for AKS.
- Dependencies and toolchains are executable supply-chain inputs. Rebuild and scan images, review package age exceptions and registry routes and pin image digests for any production deployment. Toolchain installation needing root is handled by an image/template rebuild; project code does not receive sudo.
- PVC requests on kind's local-path provisioner are scheduling claims, not reliable filesystem quotas. Monitor the Docker VM and host disk. The local idle reaper stops AI compute after five minutes and human compute after ten minutes while preserving PVCs. Capacity pressure may stop an unused AI workspace sooner; active runs and previews are protected.

## Reproduce checks

`tests/test_security.py` covers restricted manifests, ownership and pagination, safe artifact collection, Host/Origin/session/CSRF rejection and preview credential stripping. `scripts/security_probe.py` runs actual hostile-access probes from a disposable quick pod. `scripts/check_rbac.py` tests live authorization between the three namespaces. Positive chat/Coder smoke tests exercise real OpenRouter calls; a successful API response alone does not prove isolation.

## Primary references

- [Coder Agents architecture](https://coder.com/docs/ai-coder/agents)
- [Pinned Coder 2.36.4 API source](https://github.com/coder/coder/blob/v2.36.4/codersdk/chats.go)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [OpenRouter API documentation](https://openrouter.ai/docs/quickstart)
- [Go installation and versions](https://go.dev/doc/install)
- [Rust toolchain management](https://rust-lang.github.io/rustup/)

## Conversation execution and preview controls

HTTP stream disconnects detach the viewer, not the server-owned job. Results continue through ChatKit’s normal store pipeline. Cancellation is an authenticated, CSRF-protected per-conversation action. Startup marks abandoned jobs interrupted without automatically re-running arbitrary code. The local broker uses bounded response/quick execution concurrency and Kubernetes resource-version checks when leasing a warm pod.

Quick file inputs are selected from that conversation’s catalog, validated and copied into a new pod. Artifacts are immutable per run; the catalog records the latest filename version. Download and preview resolution require session ownership even for runs older than the status panel’s recent-run window. Inline PNG previews up to 8 MB are embedded as data URLs in the authenticated ChatKit response, avoiding cross-origin image requests or credentials in image URLs. Larger files remain available through authenticated artifact views. Active HTML still uses an isolated preview origin.

The Apps view embeds the stripping preview proxy in a sandboxed iframe without same-origin privileges. Developer workspace start and Ori/Pi renewal are separate human UI endpoints, never AI tools. The human UI runs as the single local lab owner and can create workspaces in the human Coder deployment. This remains a local-owner prototype, not a multi-tenant authorization system.

Chromium for chart export runs only inside the restricted pod, with its own browser sandbox disabled by Kaleido and a single-process configuration that fits the pod PID limit. Kubernetes remains the isolation boundary. Renderer MathJax downloads are disabled for offline export. Generated code retains an 8 MB file-size limit; after it exits, the supervisor renders bounded figure JSON within the remaining 30-second budget. The renderer inherits the pod limits and may create sparse temporary files, while collected exports remain capped at 8 MB each.

The embedded human VS Code frame uses the authenticated human Coder origin on port 7080 and permits same-origin capabilities needed by VS Code. It remains cross-origin from the chat UI; this exception applies only to the human IDE. Generated app/artifact frames still omit same-origin privileges and use the credential-stripping proxy. The developer App preview button targets only that owned human workspace, never an AI workspace.

## Upstream extension and package supply chain

Pi Chat is the pinned MIT upstream extension `iqbalabiyoga/pi-vscode-chat` 0.2.3, with sanitization and managed-auth/install patches. It runs Pi RPC through Ori. Its RPC process belongs to the VS Code extension host, not the main chat job queue. Reload the IDE after refreshing its limited capability. The old custom sidebar is no longer the default.

The package gateway caches only public registry metadata and artifacts; project homes and environments are separate. There is no package-name approval list; exact age exceptions last 24 hours. Public artifact IDs persist for lockfile restores. Recursive policy revocation and signed catalog provenance are future work. The five-day delay is admission policy, not a guarantee against malicious packages or against reuse of already downloaded content. Build hooks execute inside the same restricted workspace. The gateway and its external TLS connections are trusted; production should use maintained, scanned artifact mirrors with per-owner audit and durable policy controls.


## Current lifecycle and security revision

Quick reserve: five idle minutes, unassigned to any conversation. Used pods are destroyed. Quick source, artifacts and bounded working-file snapshots persist locally; no cloud storage is configured. A multi-language Coder project is allocated on `delegate_project`, or when a project chat continues existing developer source in its separate headless home. AI projects stop after five idle minutes, human workstations after ten, subject to active work and recent visible interaction. Background connections and status polling do not count. Pi Chat defaults to the right secondary sidebar and uses Ori → Pi → the trusted OpenRouter gateway. There is no package-name whitelist; only exact, expiring age exceptions. Live pod snapshots refresh every five seconds. See [the updated field guide](ARCHITECTURE-GUIDE.md) for enforcement, data paths, local credential scope and production gaps.

The local broker also keeps at most one **clean unassigned Coder project reserve** during new-chat demand. Only explicit `delegate_project` claims it. Used project homes never return to the reserve. It counts against total workspace capacity, stops after five idle minutes, and retains its unused clean home. The reserve is exposed in Lab status; set `PROJECT_WARM_RESERVE=0` to disable or `PROJECT_RESERVE_IDLE_SECONDS` to tune. AKS should replace this single-broker ledger with durable atomic leases and a demand-sized controller.

## Enterprise revision

See [ENTERPRISE-HARDENING.md](ENTERPRISE-HARDENING.md) for the threat/control matrix, Pi administrative-policy limits, protected MCP/OPA operation design and production rollout gates. Chat/title, GUI gateway and native Coder model routing use the operator settings in `config/models.env`. ZDR is temporarily disabled by explicit operator choice; `data_collection=deny` remains enabled. AWS/OpenAI are preferred and Azure is excluded for LLM requests. Account-level policy may still impose ZDR. Enable `OPENROUTER_REQUIRE_ZDR=true` before a sensitive-data pilot. The gateway validates capability audience, issue/expiry bounds and model, rejects remote content fetches and limits streamed input. There is no request-count allowance or consumption ledger. Search can be disabled with trusted `LAB_ALLOW_WEB_SEARCH=false`.

The GUI and optional Ori/Pi headless capability permits code to make its own LLM calls until expiry. Preventing that requires a trusted harness in a separate pod, remote execution tools, no model credential/route in code, and an authenticated managed-turn API. The managed Pi GUI variant is documented, **not deployed**; the native Coder headless trial already separates inference from code. No enterprise system is connected; the Rego example is not active enforcement.

## September 2026 Kubernetes hardening

The generated manifest isolates each Coder database to its corresponding Coder service. Coder control planes have default-deny policies with explicit DNS, database, workspace-agent ingress, Kubernetes API, and public HTTPS provisioning egress. Local API CIDR defaults to the kind node `172.19.0.2/32`; set `KUBE_API_NETWORK` for a different cluster. Coder public HTTPS remains available for Terraform/provider downloads and native-agent OpenRouter calls; it is not destination-filtered by this change.

Model and package gateways can no longer connect directly to public HTTPS. They use separate Squid CONNECT proxies: OpenRouter only for the model gateway; the existing registry host set for packages. CONNECT is restricted to port 443, unknown hosts and private destinations are denied, reverse-DNS domain matching is disabled, and access logs are disabled. Application validation still restricts package methods/routes and age policy. These proxies do not decrypt TLS or inspect request payloads: approved-domain tunneling and a compromised trusted proxy remain residual risks. They are a destination boundary, not a DLP system. Kubernetes node-traffic exceptions still require additional AKS/node controls.

Services now have startup, readiness and liveness probes. Startup allows three minutes before liveness begins; failed liveness requires six consecutive checks to reduce transient restart loops. Database probes use pg_isready; DNS uses CoreDNS health/ready endpoints. No snapshot schedule or image-scanning integration has been enabled. See AZURE-IMPLEMENTATION.md for bounded retention, storage growth and Snyk/GitHub follow-up.

The follow-up uses Recreate for the two PostgreSQL deployments and package cache service to avoid concurrent writers during updates. All trusted-service startup/readiness/liveness probes have explicit five-second timeouts. PostgreSQL readiness still uses pg_isready, while liveness checks that the main process exists so recovery or overload does not trigger a destructive restart loop. The former model-usage ledger is no longer mounted or used; its existing PVC is left untouched by apply (no pruning).


## Projects, documentation and approvals

Linking a developer workstation to a project never grants chat access to its live filesystem or credentials. Clicking Open in VS Code is an authenticated human action that copies bounded project source into a separate developer import directory. Unchanged source reuses that directory without replacing editor changes. Returning developer edits requires an owned source review. Active work and changed links invalidate unsafe transfers. No model or execution tool can invoke these UI-only handoffs. Opening a developer workstation does not allocate a headless sandbox.

`read_documentation` reads only named, operator-curated markdown files and explicit non-secret runtime settings. It rejects arbitrary paths and symlinks and bounds query/output size. Treat returned documents as reference data, not authority to execute instructions.

Generic approval cards show a readable excerpt and a full JSON viewer. The viewer requires ownership of the saved widget and serves escaped text on an isolated preview origin. Native confirm/cancel actions only submit a decision; the configured enforcing service must bind it to the exact tool/payload, user and expiry. Visual approval is not enforcement by itself. The private mock server and its policy remain excluded from the repository.

## Credential renewal and recovery

The local launcher rotates the quick broker's scoped Kubernetes token before expiry; execution pods still receive none. Developer model capabilities last one hour and renew only for running, recently used workspaces, via an atomic 0600 token-file replacement. Renewal does not wake or keep a workspace alive. Pi and dictation reread that file; other native harnesses may cache credentials. Coder control-plane sessions reauthenticate once after an explicit 401; simultaneous GUI refreshes share a login lock, and the AI service token file is atomically replaced. Provider API-key replacement remains an operator action; no service can mint a new OpenRouter account key.

Native Coder status-read outages reconnect within the configured turn timeout without resubmitting its message or replaying tools. Missing/deleted clean standby records are discarded so they do not block fresh allocation. Ambiguous mutations are not blindly retried. Job recovery marks interrupted turns rather than automatically repeating arbitrary code; durable distributed workers remain an AKS requirement.

Native Coder activity can expose provider-supplied reasoning text, tool arguments and aggregate reported token usage to the owning conversation. This is private conversation content, bounded for presentation, not exported to an external telemetry service or Git. It is not hidden reasoning from providers that do not expose it, and it is not a tamper-proof audit. Govern retention, redaction and access in production.
