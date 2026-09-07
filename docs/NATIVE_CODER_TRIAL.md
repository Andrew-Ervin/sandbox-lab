# Native Coder headless execution trial

This alternative is enabled locally with `PROJECT_ENGINE=coder-native` in the ignored `.env`. Developer GUI workspaces still use Pi through Ori. Quick Python keeps its existing disposable runtime.

## Request and execution path

The main chat calls `delegate_project`. The backend allocates or resumes its existing Coder workspace, transfers selected input files, and creates or continues a native Coder chat pinned to that workspace. Coder performs model inference in its control plane and sends file/shell operations over its workspace connection. The backend polls completion, returns code/tool traces and artifacts, and retains the existing app-preview and idle-stop behavior. No workspace is allocated for ordinary chat.

`scripts/configure_native_agents.py` reads the existing server-side OpenRouter credential and configures the AI-only Coder deployment. Its model and reasoning match `OPENROUTER_MODEL` and `OPENROUTER_REASONING`; the initial trial uses `openai/gpt-5.6-luna` / `xhigh`. Configuration uses `config/models.env` for provider ordering and privacy preferences. The prototype temporarily disables ZDR, retains denied data collection and prefers AWS/OpenAI while excluding Azure for model requests. The adapter rejects a model configuration mismatch instead of silently selecting another model. Run configuration again after changing the chat model.

Native Coder uses its own harness, not Ori/Pi. The installed Coder 2.36.4 exposes `/api/experimental/chats`; validate APIs before upgrading. The prototype backend uses a Coder service identity, so Coder sees that identity, while the application owns conversation authorization. Production must map Entra users to appropriately scoped Coder identities rather than infer per-user isolation from this local service identity.

## Enforced boundaries

* Headless `lab-agents` pods cannot connect to the model gateway. Their allowed egress remains filtered DNS, the package gateway, and their Coder control plane connection.
* The model gateway accepts workspace traffic only from `lab-dev` during this trial.
* Quick Python pods retain default-deny networking and receive no model credentials.
* Coder inference credentials remain in its control plane/database. The backend does not issue a model capability to headless code. Existing Pi binaries or configuration in retained project homes do not provide network access to inference.
* Headless pods run without root, privilege escalation, a Kubernetes service-account token mount, or host Docker socket. Existing CPU/memory quotas and persistent home volumes remain in effect.
* This is a Kubernetes container boundary sharing the node kernel, not a microVM or a guarantee against kernel vulnerabilities. An AKS runtime isolation decision remains separate.

The GUI workspace remains the intentional exception: its Pi/Ori capability can potentially be reused by code. Native Coder APIs also need identity authorization; do not expose an authenticated agent-session endpoint as a general inference service to execution pods.

## Scope and limitations

Existing project files are reused, but old Pi reasoning history is not imported into the new native Coder conversation. New native turns retain their own history. The frontend and preview lifecycle are unchanged. A stopped project's files remain; opening its app still uses the stored launch recipe without an LLM call.

The temporary mock-email approval bridge is not connected to native Coder in this trial. Main-chat approvals and GUI Pi retain their previous implementations. Native chat requests select no MCP servers and instruct the trial agent not to invoke MCP tools; this instruction is not a replacement for production server-side MCP authorization. Do not enable native MCP integrations before connecting their approval enforcement.

## Validation

The local trial exercised native file creation, `uv run` execution, and artifact return. Independent probes verified blocked headless access to the model gateway, direct OpenRouter, and public HTTPS; package gateway health remained available. The workspace identity received HTTP 401 from the native model API. Quick Python could not connect to the model gateway or public HTTPS and contained no model credential environment variables. Private test evidence resides in `.local/native-coder-trial/` and must not be committed.

## Reversal

`python .local/native-coder-trial/rollback.py` checks the trial's file hashes without changing anything. After stopping the local app launcher, add `--execute` to restore only snapshotted source/settings and network policies, disable the native trial provider, and retain all conversations, projects, and files. Restart `python scripts/start.py`. The rollback refuses to overwrite subsequent edits. Do not commit `.local`, `.env`, Coder database contents, provider credentials, or workspace files.


## Enabling on a fresh checkout

The checked-in `.env.example` defaults to `PROJECT_ENGINE=ori-pi`. Finish the ordinary local bootstrap, stop the app with no active jobs, set `PROJECT_ENGINE=coder-native` in `.env`, then regenerate/apply the infrastructure so headless model egress is removed. Keep Coder forwarding available and run `scripts/configure_agents.py`, then `scripts/configure_native_agents.py`. The latter creates the `lab-openrouter` provider if absent, or refreshes it if present. Start the backend and repeat the isolation probes. Changing only the environment flag is insufficient: the rendered policies and provider configuration must match.

The reversal script above belongs to the original machine's ignored experiment, not a fresh checkout. On another installation, review and change the engine, regenerate/apply policies and reconfigure providers deliberately. Never copy private rollback snapshots between users. See [the pinned Coder provider schema](https://github.com/coder/coder/tree/v2.36.4/codersdk) and validate it when changing Coder releases.

## Activity inside main chat

The collapsible execution card now receives live Coder message activity approximately every five seconds: provider-supplied reasoning text, tool names/arguments, completion/failure state and available input/output/reasoning/cache token counts. Availability follows the provider and Coder's persistence timing; partial tokens are not streamed before Coder exposes them. The final card retains the bounded activity with the conversation. Status/gallery polls omit the detailed trace. These counters are diagnostic, not a billing ledger. No extra model credential or network route is added to the execution sandbox.

Reference: [Coder chat message and usage schema](https://github.com/coder/coder/blob/main/codersdk/chats.go).

## Turn control and result recovery

The bottom code-session strip independently polls the native Coder chat. Stop coding calls its interrupt endpoint after ownership and session checks, then stops headless workspace compute to terminate any surviving shell children. It works even if the main chat response has already ended. Unknown connections retain active-workspace protection, and the next coding task cannot overlap with an unfinished turn in that project. Same-project chats can show the active sibling session. Stopping retains source, closes existing headless app previews, and leaves the separate GUI workstation alone. Apps can restart on their next open.

Coder GET requests retry transient transport and 429/502/503/504 failures. POST prompts and tool actions are not blindly replayed. Completed native work is not reclassified as failed merely because the model's final prose or artifact collection disconnected. Artifact reads retry once; if still unavailable, the project remains accessible. The bounded live activity view contains only reasoning explicitly returned by the provider, tool metadata and reported token counts.
