# Developer coding tools

When the operator enables `workspace_mcp_learn`, workspace setup registers a
fixed Microsoft Learn MCP client for Claude and Codex and installs `lab-learn
search "question"` for Pi's terminal tool. It forwards only the three approved
documentation tools to Microsoft's public endpoint. No credentials, dynamic
package installation or general HTTP proxy are added. Normal tool approval
settings remain intact. Existing workspaces receive it on harness refresh/open;
native sessions already running may need to restart to discover it. Turning the
runtime flag off revokes network access on the next harness refresh, even if a
saved client entry remains. See the [examples](../infra/azure-sandbox-pilot/examples/README.md).

Developer workstations use browser-based VS Code with pinned Pi Chat, Claude Code and Codex extensions. `piChat.piPath` points at `ori-lab`. Its RPC session, tool execution, developer history and files stay in the GUI home. Main-app headless coding uses its separate project home and local broker inference.

The setup supplies `pi-lab`, `ori-lab`, `claude-lab`, `codex-lab`, and `ori-code-lab` terminal entry points. Bare `pi`, `codex`, and `claude` commands also enter the corresponding Ori wrapper. Ori launches the pinned real harness through private adapters, avoiding recursive wrapper discovery. Model requests route only through the local reverse gateway to the configured OpenRouter model. Upstream keys are not written into the workspace. The signed GUI token expires and is renewed only for active workstations. Approval and package-age controls remain enabled.

The Extensions search uses a managed local gallery of reviewed, checksum-pinned official Open VSX packages. Claude Code and Codex are supplied automatically; additional extensions require an approved pin. Five-day release age and checksum checks apply to both setup and gallery downloads. Auto-update checks are disabled. The editor opens as soon as it is healthy; agent preparation reports its own status and may finish afterward. A stable IDE preview origin preserves folder-specific browser trust across resumes. The preview proxy explicitly supports the VS Code service worker and same-origin webviews.

GitHub Copilot's signed-in extension flow is disabled. The pinned CLI uses offline BYOK mode through the same OpenRouter gateway and has passed a live response test without GitHub sign-in. If installation of that approved build fails, its launcher is blocked; see [GitHub BYOK documentation](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models). Direct GitHub/model egress remains denied regardless of CLI settings.

Pi's fixed CSS and JavaScript assets are embedded into its nonce-protected webview document. This avoids external VS Code asset origins while retaining the restrictive preview policy. `scripts/patch_pi_webview.py` applies this repeatably during extension builds.

Do not use permissive flags, trust parent folders, bypass TLS validation, or relax package policy to resolve startup errors. Inspect the developer setup error, code-server extension logs and the browser webview console. An open editor shell alone does not prove Pi Chat works.

The native Claude panel uses `claudeCode.claudeProcessWrapper`; the Codex panel uses `chatgpt.cliExecutable`. Both launch the corresponding Ori wrapper and preserve the extension stdio protocol and approval options. Claude sessions appear under its activity-bar icon. Codex is available through **Open Codex Sidebar** and the secondary-sidebar view menu. No vendor sign-in is needed for the configured OpenRouter path.

The editor preview supports VS Code's virtual resource host only for files under the installed-extension directory. This preserves webview asset loading without giving generated app previews external access. Model requests and observed editor activity renew the IDE listener; merely polling status does not.

Personal settings synchronize at editor start, on active-workspace heartbeats (at most once per 30 seconds), on explicit Save editor preferences, and before stop. JSONC settings and keybindings preserve personal appearance/editor preferences while retaining local security and model configuration. A per-owner baseline merges changes from multiple workstations. Reviewed browser layout keys synchronize on a 15-second visible-editor interval. Installed extension identities are recorded; the approved pinned extensions are installed in every workstation. This does not enable arbitrary marketplace installation or copy extensions’ private global state. Native chats, tokens, trust decisions and workspace-specific state are not part of the shared profile.

Direct editor origins retain their listener for ten minutes, matching workspace idle policy. A small editor-side input listener reports new visible keyboard/pointer/wheel activity every 15 seconds at most; it does not continually mark an untouched editor active. Model calls also renew the listener. This covers editors opened outside the main app’s preview panel.

Workspace setup refreshes the public OpenRouter catalog and exposes text-output models with finite nonnegative token prices. Luna remains the initial model. Signed capabilities reference the broker's catalog instead of carrying thousands of IDs in headers. The broker reserves cost using the selected model's prices and rejects unknown or stale prices; provider-policy restrictions still apply. Pi and Claude defaults are no longer overwritten on refresh. Ori's Claude/Codex wrappers read the user's saved model and allow an explicit command-line override. Different models may not support every coding protocol/tool feature.
