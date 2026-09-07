# MCP authorization contract example

`mcp.rego` is a deny-by-default **design example, not an enabled integration**. No enterprise MCP server or database is connected to this prototype. Validate/adapt this policy to your entitlement system before deployment.

Run with OPA 1.x:

```sh
opa test infra/policy -v
```

The trusted broker assembles OPA input from verified Entra identity, its signed tool catalog, project ownership, a canonical operation plan, current resource version, and its own approval store. None of `identity`, `catalog`, `context`, or `approval` comes from model arguments or an unverified HTTP header. `approval.verified` means the broker already authenticated the approval record/signature; Rego does not validate a signature here.

The gateway accepts only the exact response `result: true` from the allow query. Undefined, false, timeout, malformed response, stale bundle, or untrusted connection means deny. Protect the OPA channel with workload authentication. Mask decision log inputs; do not log secrets, raw prompts, SQL values, or datasets.

Before executing a write, the broker must atomically reserve/consume the approval nonce, recheck authorization and resource version, enforce row limits in the transaction, and supply an idempotency key. A boolean policy decision does not provide atomicity, prevent concurrent replay, or execute a database transaction. Persist outcomes and reject uncertain retries until reconciled.

The action hash covers tenant, subject, project, environment, tool/version, normalized parameters, target IDs, dry-run result, resource versions, policy version and expiry. Review the exact operation in a trusted human UI outside chat. Require independent approvers; production/delete operations in this example need two distinct authorized reviewers. Production additionally requires a verified change record. Remove production write entitlements entirely for the first pilot.

MCP authentication must validate the intended audience/resource. Do not forward a model-supplied token or reuse the incoming MCP token as a database token. Use a separate narrowly scoped destination identity, delegated user flow where supported, or a tightly constrained service identity with enforced user entitlements. See [enterprise hardening](../../docs/ENTERPRISE-HARDENING.md).
