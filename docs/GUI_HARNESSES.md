# GUI harness trial

The `developer` workspace is the native-extension trial. Pi/Ori remains the default chat sidebar. Claude Code and Codex native extensions use the same fixed OpenRouter gateway/model, through their own supported provider configuration. Ori wraps the terminal profiles; it is not the launcher for the native extensions' bundled processes.

Pinned CLI versions: Claude Code 2.1.258, Codex 0.152.1. Ori installed version: 0.14.1+5bb4241. Ori's Claude/Codex launchers hardcode OpenRouter URLs at this version, so terminal adapters rewrite only the provider base URL to our gateway. Ori Code honors ORI_OPENROUTER_BASE_URL.

The gateway supports Chat Completions, Responses, and Anthropic Messages. All routes require the same signed capability and fix the upstream model and operator-controlled routing/privacy policy from `config/models.env`. Native routes permit local tools, not remote MCP/server tools or URL attachments. GUI capabilities remain accessible to GUI user code; they are not an executable identity boundary. Native Coder execution pods have no route or model capability.

Native extension packages are privately cached under `.local/gui-harness-trial`, excluded from Git. Pinning and download checks use Open VSX publication age and SHA-256. The user approved increasing the package artifact limit to 250 MB for large harness binaries; the five-day age gate is unchanged. `scripts/configure_developer.py --workspace NAME` provisions pinned native extensions and CLI profiles. The earlier `scripts/provision_codex_binary.py --pod POD` remains an optional administrator path with publication-age and SHA-512 verification.

Claude optional telemetry, feedback, official marketplace auto-install and updates are disabled. Its WebFetch domain preflight is disabled too. Codex analytics, feedback and update checks are disabled. Direct vendor egress remains denied regardless of client settings. These settings do not promise zero provider-side processing: the selected model still receives inference through OpenRouter under the configured provider policy.

## Hermes and OpenCode

Neither is installed in this trial. Hermes has an explicit opt-in shared-metrics exporter to Nous; its documented default is off. This is not evidence of default telemetry when using OpenRouter. OpenCode documents direct provider communication and optional conversation sharing; its official IDE integration is a terminal integration, not a comparable native chat sidebar. No blanket zero-telemetry certification has been established for either harness here.

- [Hermes telemetry exporter and consent design](https://github.com/NousResearch/hermes-agent/pull/95278)
- [OpenCode enterprise data/sharing policy](https://opencode.ai/docs/enterprise/)
- [OpenCode IDE integration](https://opencode.ai/docs/ide/)
- [Claude Code supported surfaces](https://code.claude.com/docs/en/platforms)
- [Claude Code data usage](https://code.claude.com/docs/en/data-usage)
- [Codex IDE configuration](https://learn.chatgpt.com/docs/developer-settings?surface=ide)
- [Codex custom provider configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)
- [Ori configuration](https://openrouter.ai/docs/guides/ori/configuration)

For APIM separation and the limits of harness attribution, see [APIM_HARNESS_BOUNDARY.md](APIM_HARNESS_BOUNDARY.md).

## Verified locally

Claude Code and Codex native chat panels loaded inside the embedded browser-based code-server and returned responses. The synthetic native Claude test returned `NATIVE_CLAUDE_OK`. Terminal Ori launch tests passed for Claude Code, Codex and Ori Code. Ori Code’s optional global dashboard feature is currently degraded because Bun/dashboard dependencies are not installed; its coding chat responded successfully. Headless direct-inference checks still failed closed after adding the GUI gateway protocols. Gateway, package, and native-Coder regression tests: 32 passed.

## Pi microphone dictation

Pi Chat has an opt-in microphone button. Record for up to five minutes, or click again to stop. The transcript is inserted into the draft for review, never automatically sent. Cancel discards the recording. Audio is held in memory, converted in the browser to mono PCM16 WAV at 16 kHz and capped at 10 MB, and sent through the authenticated gateway to OpenRouter's `microsoft/mai-transcribe-2` transcription endpoint. No upstream credential reaches the webview. The current provider rejected WebM in a live synthetic-speech test, so browser container formats are decoded/resampled before upload. Limits are in `config/limits.env`; see `LIMITS.md` for deployment steps.

When `OPENROUTER_REQUIRE_ZDR=true`, the gateway checks before uploading audio that every currently advertised model endpoint appears in OpenRouter's ZDR endpoint list; unavailable or ambiguous metadata fails closed. ZDR is temporarily disabled for this prototype. Speech uses its separate Azure endpoint; the LLM Azure exclusion does not apply to transcription. This metadata check is not an atomic routing guarantee. Production should also enforce account-level retention policy. Browser microphone permission and HTTPS (or localhost) are required. The application delegates microphone access only to the developer IDE iframe.

Active GUI credentials renew before their one-hour expiry without restarting Pi. The trusted host replaces the capability file atomically; Pi’s provider reads it per request and dictation per recording. Renewal does not wake idle workspaces. Claude/Codex or other native clients may cache a credential; start a fresh terminal/session if they keep an expired value. See SECURITY.md and LIMITS.md.
