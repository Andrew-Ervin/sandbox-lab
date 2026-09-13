# Identity and personal settings

The pilot uses a single-tenant Microsoft Entra web registration with the callback `http://127.0.0.1:3000/api/auth/callback`. It requests OpenID basic identity scopes, not mailbox, directory-read or Azure management permissions. The registration itself creates no compute resource or fixed hosting charge.

Private `.local/entra.json` contains `tenant_id`, `client_id`, `client_secret`, `admin_oid` and `redirect_uri`. Never publish this file. The current pilot secret expires on **2026-12-13** and must be rotated through Entra before then. The local callback is for the local pilot; a public deployment needs HTTPS, secure cookies, a reviewed redirect origin and a shared session store.

The server uses authorization code + PKCE, a browser-bound one-time state and nonce, tenant-pinned JWKS, RS256 signature verification, audience/issuer checks and token lifetime checks. It discards provider tokens after sign-in and retains a private revocable session. The session lifetime is bounded by eight hours and the validated ID-token expiration. Signing out revokes that app session; an existing Microsoft browser session may make the next sign-in immediate.

An account is identified by `entra:<tenant ID>:<object ID>`, not display name or email. API lists and mutations enforce that owner. Preview listeners enforce the same owner and websockets recheck session validity. The configured operator alone can view infrastructure operations or change package policy. First sign-in by another person cannot claim historical data.

On first activation, SQLite history and workspace metadata are backed up in private `.local/identity-backups/`. Legacy `local-owner` records are assigned to the preselected operator identity, then marked migrated. Saved generated files and cloud homes are preserved. A clean source installation with no Entra configuration is explicitly local-owner mode; a present but invalid configuration fails startup rather than silently issuing anonymous sessions.

Editor profiles are stored per owner in the local workspace database. Appearance/editor preferences and keybindings follow the user, including existing workspaces when they next launch. Per-workspace baselines prevent an older open workspace from overwriting newer preferences wholesale. Selected browser layout keys are copied without copying chat state, secrets, trust decisions or arbitrary extension state. The approved pinned extensions are available in each workstation; this feature does not bypass the managed gallery or package-age policy.

This is application-level isolation on one trusted operator’s local broker. It is not isolation from the operator, not encrypted multi-tenant storage on the local machine, and not a production distributed identity deployment.
