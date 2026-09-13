# Workspace MCP and narrowly scoped GitHub access

These examples keep provider credentials out of images and source. They do not
change a live workspace when imported or when printing a plan. Run the policy
generator with the isolated Azure Sandbox SDK Python; it uses the installed
SDK's wire serializer. Keep operator configuration under ignored local state.

## 1. Native Sandbox managed MCP connectors

This is the platform's default integration, distinct from opening an internet
host in an egress rule. The native flow needs a Connector Namespace and an
authenticated connection. Start with a Microsoft connector such as Azure Blob
Storage using a dedicated read-only test container, or register the public
Microsoft Learn hosted MCP server if the namespace's catalog supports it. The
catalog and available operations must be inspected before selecting them.

1. Use a work/school account at `https://connectors.azure.com`. Create or select
   a Connector Namespace only after its regional pricing is reviewed. This
   repository does not assume the preview service is free.
2. Select the Microsoft connector and separately the GitHub connector. Configure
   only the required read operations. For Blob, scope authorization to the test
   container; for GitHub, scope it to the intended repository. Complete consent
   in the provider UI. Do not use a shared operator credential for all app users.
3. Copy the resulting MCP ARM IDs, ending in
   `Microsoft.Web/connectorGateways/<namespace>/mcpserverconfigs/<name>`.
4. Select the intended sandbox group in the ACA CLI, attach its managed identity,
   and attach each reviewed connector. The documented commands are:

```sh
aca sandboxgroup connector add --connection-id "$MICROSOFT_MCP_ID" --authorization system
aca sandboxgroup connector add --connection-id "$GITHUB_MCP_ID" --authorization system
aca sandboxgroup connector list
```

Use a separate group for a separate permission boundary. The connector's upstream
account is not automatically the Entra user who signs into Sandbox Lab.

Generate the SDK creation arguments without allocating anything:

```sh
.local/azure-pilot/sdk-venv/bin/python infra/azure-sandbox-pilot/examples/workspace_mcp.py \
  --mode native --connection-id "$MICROSOFT_MCP_ID" --connection-id "$GITHUB_MCP_ID"
```

The returned `connections` list belongs in `SandboxGroupClient.begin_create_sandbox`.
For the platform's built-in image integration, the equivalent CLI creation is:

```sh
aca sandbox create --disk claude --label name=mcp-example \
  --connection-id "$MICROSOFT_MCP_ID" "$GITHUB_MCP_ID"
```

Review the selected group's CPU, timeout and budget before running creation.
The native sample uses the platform Claude image to exercise its auto-generated
agent configuration; it does not run Copilot, grant blanket tool approval, or
replace this app's custom image. Inspect the generated MCP configuration and
test tool discovery plus a read operation before porting it to our custom image.
The current app runtime does **not** automatically adopt the generated config.

Connectors must be attached to the group first. Individual sandboxes opt in at
creation, with at most ten IDs; this selection is immutable. Do not delete an
existing workspace to retrofit it. Plan a replacement that preserves its files,
and exclude privileged workspaces from a generic cross-user warm pool.

Validation status: configuration arguments checked against the installed SDK.
Live native connector deployment is deferred. Direct Learn MCP is the selected pilot path; the managed route requires a compatible account and a pricing review.

## 2. Direct Microsoft Learn MCP through a narrow egress allowlist

Set `workspace_mcp_learn: true` in the private runtime configuration to provision this integration for developer workspaces. The broker installs the fixed-endpoint stdio bridge for Claude and Codex and a `lab-learn search` command for Pi. Existing client settings are preserved. Live validation confirmed Claude connectivity, Codex discovery, and a Pi browser chat executing a documentation search and returning a link. This does not require a Connector Namespace or a new image build.

This works without a Connector Namespace or an upstream credential. It uses
Microsoft's hosted MCP server as shipped, including runtime tool discovery.

```sh
.local/azure-pilot/sdk-venv/bin/python infra/azure-sandbox-pilot/examples/workspace_mcp.py --mode remote
```

The operator applies `remote_mcp()` with the SDK's
`sandbox.set_egress_policy(policy)`, or passes it at creation. This is a complete
policy: review existing required rules before replacing a live policy. It permits
only the Learn MCP endpoint's GET/POST/DELETE transport, with Full inspection and
default Deny. DELETE ends MCP transport sessions; it does not grant Azure resource
deletion. Package sources and other hosts remain closed.

Copy `microsoft-learn.mcp.json` to a test project's `.vscode/mcp.json` for a client
that supports the VS Code MCP configuration. This does not enable or authenticate
Copilot. Other clients use their own MCP configuration format. Our Pi integration
does not gain native MCP discovery merely from that file. The included Python
probe provides a common terminal-level verification independent of any model.

Run inside the sandbox:

```sh
python mcp_probe.py
```

The probe initializes MCP, discovers tools, checks the search schema, and executes
one documentation search. It excludes the package proxy for this explicitly
allowed endpoint; the platform egress engine still enforces the policy. A native
client inheriting our package proxy needs an equally narrow `NO_PROXY` entry for
`learn.microsoft.com`, not a global proxy bypass. Keep TLS verification enabled.

Live validation: Microsoft Learn reported `microsoft_docs_search`,
`microsoft_code_sample_search`, and `microsoft_docs_fetch`; a real documentation
search succeeded from a disposable sandbox. An unapproved host returned HTTP 403.
The test sandbox was deleted. This is protocol-level verification, not a claim
that every coding-agent panel has been configured and tested.

Optionally add `--github-secret github-read-token` to generate the hosted GitHub
MCP rule. The token is a **secret reference**, never its value. The policy injects
read-only/toolset headers. The credential must also restrict permissions: headers
alone are not a repository authorization boundary. This authenticated variant
has not been live-tested.

## 3. Allow a specific GitHub PR write from the sandbox

Store a short-lived, repository-scoped GitHub App installation token or fine-grained
PAT in the sandbox group's secret store. Grant only the necessary Pull requests
permission on the chosen repository. Keep token creation/renewal in the trusted
operator path. Do not reuse the host's general Git credential or mount `.git-credentials`.

```sh
.local/azure-pilot/sdk-venv/bin/python infra/azure-sandbox-pilot/examples/workspace_mcp.py \
  --mode pr --owner example-owner --repo example-repo --github-secret github-pr-token
```

Apply this reviewed policy to the dedicated test sandbox. `github_pr.py` runs
inside it; authorization is injected by Azure's egress proxy. It prints a plan
until `--submit` is supplied:

```sh
python github_pr.py --owner example-owner --repo example-repo \
  --head feature-branch --title 'Review sandbox changes'
# After the user requests this concrete publication:
python github_pr.py --owner example-owner --repo example-repo \
  --head feature-branch --title 'Review sandbox changes' --submit
```

The head branch must already exist on GitHub. This example does not grant Git
push, merge, deletion, or repository administration. After creation, the operator
can generate a policy with `--review-number N` and apply it to allow the specific
`POST /repos/OWNER/REPO/pulls/N/requested_reviewers` path. Then:

```sh
python github_pr.py --owner example-owner --repo example-repo \
  --review-number 12 --reviewer reviewer-login --submit
```

GitHub's ordinary reviewer API may reject the Copilot app as a non-collaborator.
Use GitHub's supported Copilot review UI when that occurs; do not substitute an
issue comment that asks the coding agent to modify the PR. PR creation and an
ordinary reviewer request are the transport example; Copilot's specialized
review flow is a separate capability.

HTTP paths and methods cannot inspect the PR body or provide human approval.
Anyone able to execute in that sandbox could use its granted write operation.
Use a dedicated short-lived grant and an approval-aware broker for production.
Test denied methods and alternate repository paths before using real credentials.
A timed-out write is never retried automatically: reconcile its outcome first.

## Cost and lifecycle

The verified 1 CPU / 2 GiB sandbox test rate is $0.108/hour, or $0.018 for ten
minutes of active compute, before storage/network charges. The live Learn probe
used about $0.00033 of estimated compute. The probe did not invoke an LLM.
Native connector charges remain unverified; do not deploy that service under
the test budget until reviewed. No new fixed-charge resource is needed for the
direct Learn route. Revoke temporary write policies when the task finishes.

Sources: [Native Sandbox connectors](https://sandboxes.azure.com/docs/sandboxes/connectors),
[Connector Namespace CLI](https://github.com/Azure/Connectors/blob/main/public-preview/connector-namespace-cli/README.md),
[Learn MCP](https://learn.microsoft.com/en-us/training/support/mcp-developer-reference),
[GitHub hosted MCP](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md),
[Sandbox egress](https://learn.microsoft.com/en-us/azure/container-apps/sandboxes-egress-policies).
