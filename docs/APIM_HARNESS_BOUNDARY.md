# APIM: coding-tool access versus AI-application access

APIM can authenticate and authorize a caller, but cannot reliably infer the originating executable or human intent from a model request. User-Agent, harness names, session IDs, telemetry headers, prompt structure, tool schemas, and timing are reproducible by a script. Entra public-client application IDs are not proof that an unmodified approved executable originated a request. A stolen/reused valid bearer token retains its claims.

## Two distinct controls

* Vendor telemetry (analytics, crash reports, updates) goes to separate destinations. Disable it in the harness and deny those destinations at the egress boundary. APIM sees this traffic only if it is explicitly routed through APIM; an inference gateway does not automatically intercept every outbound connection.
* Inference authorization requires a trusted identity boundary. Only a broker/controller outside the code sandbox should possess the coding-tool inference identity. APIM validates that identity and its audience/role; execution pods have neither its token nor network access to its endpoint.

## Proposed enterprise deployment

1. `CodingTools.Use`: user may invoke an approved coding session through the application. A trusted agent controller authenticates to the coding APIM API using a workload identity. Bind a verified end-user identity to each session for authorization and audit; never trust a client-supplied user header.
2. Agent tools execute in a separate pod without model credentials, controller credentials, or direct inference routes. Its permitted tool API cannot serve as a generic inference proxy.
3. `AIApplications.Develop`: separately authorized users obtain an application-specific Entra identity/audience for a separate APIM AI-development API. Use independent budgets, model policy and audit attribution.
4. APIM validates tokens, audiences and required roles/scopes. Private networking and optionally mTLS constrain trusted callers. Certificate keys/token files must stay outside the untrusted execution environment.
5. The backend holds the OpenRouter secret; neither route distributes it to users. Preserve ZDR/provider policy and suppress sensitive request-body logging.

GUI workspaces running both the extension and arbitrary user code under the same identity do not provide this separation. Adding a token, mTLS certificate or sidecar accessible by that code does not fix it. Separate containers in the same pod share networking; Kubernetes NetworkPolicy alone cannot distinguish their processes. A remote agent controller can keep a sidebar UI, but requires a supported remote protocol/integration and independently authorized tool execution.

For the current GUI exception, monitoring/classification can flag likely AI-application use, but is probabilistic. Treat automated rejection as a policy heuristic with false positives and evasion, not a hard security guarantee.

## Native Coder verification

On 2026-09-06/07, a Python probe executed inside the native Coder workspace observed: model credentials absent; direct OpenRouter and local model gateway requests blocked; CONNECT through the package proxy rejected with HTTP 403; the actual populated Coder agent token rejected with HTTP 401 when used to POST to the native chat API. This verifies the tested direct-inference paths, not every possible future service or an inability to write source containing LLM calls. Re-test whenever network rules, credentials or tools change.

## References

- [APIM Entra token validation](https://learn.microsoft.com/en-us/azure/api-management/validate-azure-ad-token-policy)
- [APIM client certificate validation](https://learn.microsoft.com/en-us/azure/api-management/validate-client-certificate-policy)
- [Claude Code telemetry controls](https://code.claude.com/docs/en/data-usage)
- [Ori configuration](https://openrouter.ai/docs/guides/ori/configuration)
