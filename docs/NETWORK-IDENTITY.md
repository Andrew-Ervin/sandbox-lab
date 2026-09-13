# Network controls and workload identity

The live Sandbox runtime creates every allocation with `EgressPolicy(default_action='Deny', traffic_inspection='Full')` in `scripts/azure_sandbox_rpc.py`. Package and model traffic uses authenticated reverse services to the trusted broker; arbitrary direct outbound traffic is denied. An operator can enable `workspace_mcp_learn: true` in private runtime configuration to allow only the Microsoft Learn MCP endpoint for developer workspaces. The package broker retains its release-age and approved-source checks. This applies to ACA **Sandboxes**, not ordinary Container Apps or AKS pods.

The [MCP examples](../infra/azure-sandbox-pilot/examples/README.md) cover native connector attachment, direct Microsoft Learn and GitHub MCP, and a separate repository-scoped PR write policy. The direct Learn path is enabled in the pilot. Native Connector Namespace deployment is deferred by operator choice. The [service comparison](CONTAINER-APPS-CHOICE.md) explains what a regular Container App would replace and what remains application work.

## Domain filtering example

`infra/azure-sandbox-pilot/examples/network_policy.py` prints two SDK policy objects without contacting Azure. The source-read example permits GET/HEAD to explicit GitHub, Azure DevOps and Python package hosts and denies everything else. Full inspection blocks non-HTTP traffic. The example is not attached to any live sandbox. HTTPS Git clone can need POST upload-pack; authentication, redirects, LFS and organization-specific package hosts need separately reviewed rules. A host allowlist alone does not prevent uploading secrets to that allowed host. Use narrow paths and methods where possible.

Direct PyPI access would bypass this app's package-age gate. Keep the live broker route unless replacing that gate with equivalent enforcement. Azure's Partial inspection allows non-HTTP traffic, so it is not equivalent to Full/default-deny. Existing connections and in-flight requests also need consideration during policy changes.

## Identity example

`infra/azure-sandbox-pilot/examples/read-only-identity.bicep` defines an empty group with a system-assigned identity and grants Storage Blob Data Reader only on one existing Blob container. It accepts resource names as parameters; no subscription IDs or personal configuration are embedded. It has not been deployed. The SDK example also demonstrates managed-identity Authorization-header injection to one API host for GET/HEAD. Configure the audience and API role for the intended API before use.

A Sandbox group can use a system- or user-assigned managed identity for gateway connections and registries. Egress transformations can acquire and inject an identity token without handing the token to workload code. This is group-scoped: do not share a privileged group among users who must have different resource permissions. Separate groups/identities or a user-aware authorization broker are needed for those boundaries. The identity's target-resource permissions are distinct from the operator's SandboxGroup Data Owner role. Ordinary Container Apps also support managed identity, through a different workload identity surface. This example does not assert that a generic IMDS endpoint exists inside Sandboxes.

## Ori and APIM

Yes, Ori can route through APIM. Our Ori adapters already replace provider endpoints with a local protocol gateway. The trusted gateway currently sends requests directly to OpenRouter; it is **not already routed through APIM**. Pointing that trusted upstream at APIM, supplying its appropriate credential/identity, and configuring APIM to forward the required paths supports the same architecture without exposing upstream keys in the workstation. Preserve streaming, tool-call payloads, request limits and timeouts. Pi uses chat completions, Codex uses Responses, and Claude uses Messages; APIM must support each route used, not only a chat-completions policy. No APIM resource or routing change was made in this round.

Ordinary ACA domain egress filtering generally uses VNet routing and a firewall/proxy architecture. That is a different deployment from the Sandbox built-in egress engine. Firewall/APIM tiers can introduce fixed charges and require approval under the testing budget before deployment.

References: [Sandbox egress controls](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-egress-policies), [Sandbox groups and identity](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-quickstart-bicep), [Container Apps identity](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity), [Container Apps with Azure Firewall](https://learn.microsoft.com/en-us/azure/container-apps/use-azure-firewall).
