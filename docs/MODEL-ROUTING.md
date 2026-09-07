# Model routing and privacy

Edit `config/models.env` for public defaults; process environment and private `.env` override it. The current temporary prototype policy is:

| Setting | Default | Behavior |
| --- | --- | --- |
| `OPENROUTER_PROVIDER_ORDER` | `amazon-bedrock,openai` | Prefer AWS, then OpenAI; unavailable/incompatible endpoints are skipped. |
| `OPENROUTER_PROVIDER_IGNORE` | `azure` | Exclude Azure and its regional variants for model requests. |
| `OPENROUTER_REQUIRE_ZDR` | `false` | ZDR is temporarily not required by this application, by operator choice. |
| `OPENROUTER_DATA_COLLECTION` | `deny` | Continue denying provider data collection. |

Fallbacks remain enabled among eligible providers. No synthetic message-count quota is applied. Provider errors can still include upstream 429 responses; that is not evidence of an OpenRouter-wide message limit. Main chat retries transient upstream errors up to `CHAT_PROVIDER_ATTEMPTS` before reporting failure. Provider selection does not change the selected model or reasoning effort.

The shared policy module is `sandbox/model_policy.py`. Main chat (including titles), the GUI model gateway (Chat Completions, Responses and Messages), and native Coder configuration all use it. Workstation requests cannot override the gateway's policy. Quick and native Coder execution pods still have no LLM credential or network route; these changes do not alter those boundaries.

After an edit:

1. Restart the local backend.
2. Run `scripts/render_infra.py` with the deployed `PROJECT_ENGINE`, then apply the gateway ConfigMap and Deployment and restart the gateway. Inspect the rendered diff before applying other resources.
3. Run `scripts/configure_native_agents.py` for native Coder. This updates the control-plane model configuration without copying the key into execution pods.

Speech is separate: `microsoft/mai-transcribe-2` currently uses Azure. OpenRouter's transcription API does not honor LLM provider ordering. When ZDR is enabled, the gateway verifies all advertised speech endpoints against the ZDR catalog before uploading; failures deny the upload. With ZDR disabled that check is skipped. Dictation still keeps audio in memory and returns text to the draft.

Re-enable `OPENROUTER_REQUIRE_ZDR=true` and the corresponding account/enterprise gateway policy before a sensitive-data rollout. Account-level OpenRouter policy can remain stricter than a request; `false` does not override an account requirement. Denied data collection alone is not a claim of zero retention, and neither setting prevents disclosure of content intentionally sent to a model or search provider.

References: [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [ZDR controls](https://openrouter.ai/docs/guides/features/zdr).

## Exa search and citations

Main chat and the Ori/Pi Chat Completions gateway offer OpenRouter's `openrouter:web_search` server tool with `engine=exa`. The model chooses whether to search. OpenRouter executes search; coding pods receive no direct web access. `LAB_ALLOW_WEB_SEARCH=false` disables this path. Bounds live in `config/limits.env`: three results per search, six total and two uses per model request. A multi-step assistant turn can make several model requests. Conversation title generation never enables search.

The backend maps actual OpenRouter `url_citation` annotations to ChatKit `Annotation` / `URLSource` objects. ChatKit renders its native Sources control and source links; saved citations survive reload. Unsafe URL schemes and credential-bearing URLs are discarded; missing/invalid offsets fall back to a source-list entry. The backend does not invent citations from arbitrary Markdown links. Older answers without provider annotations cannot gain verified citations through a presentation migration.

Search queries and selected model context leave the trusted application through approved providers. The switch and network boundary do not provide content DLP. Apply enterprise query minimization, classification and contractual controls before sensitive use. The native Coder harness and other provider protocols have their own tool support; this change does not promise an Exa tool in every native extension.

Reference: [OpenRouter server web search](https://openrouter.ai/docs/guides/features/server-tools/web-search).
