# Identity and personal settings

The pilot uses a single-tenant Microsoft Entra web registration with the callback `http://127.0.0.1:3000/api/auth/callback`. It requests OpenID basic identity scopes, not mailbox, directory-read or Azure management permissions. The registration itself creates no compute resource or fixed hosting charge.

Private `.local/entra.json` contains `tenant_id`, `client_id`, `client_secret`, `admin_oid` and `redirect_uri`. Never publish this file. Track the configured secret expiry privately and rotate it through Entra before expiration. The local callback is for the local pilot; a public deployment needs HTTPS, secure cookies, a reviewed redirect origin and a shared session store.

The server uses authorization code + PKCE, a browser-bound one-time state and nonce, tenant-pinned JWKS, RS256 signature verification, audience/issuer checks and token lifetime checks. It retains a private revocable session and a server-only refresh token when Microsoft issues one. Access requires a currently validated identity token, renewed within an absolute eight-hour session lifetime. Signing out revokes that app session; an existing Microsoft browser session may make the next sign-in immediate.

An account is identified by `entra:<tenant ID>:<object ID>`, not display name or email. API lists and mutations enforce that owner. Preview listeners enforce the same owner and websockets recheck session validity. The configured operator alone can view infrastructure operations or change package policy. First sign-in by another person cannot claim historical data.

On first activation, SQLite history and workspace metadata are backed up in private `.local/identity-backups/`. Legacy `local-owner` records are assigned to the preselected operator identity, then marked migrated. Saved generated files and cloud homes are preserved. A clean source installation with no Entra configuration is explicitly local-owner mode; a present but invalid configuration fails startup rather than silently issuing anonymous sessions.

Editor profiles are stored per owner in the local workspace database. Appearance/editor preferences and keybindings follow the user, including existing workspaces when they next launch. Per-workspace baselines prevent an older open workspace from overwriting newer preferences wholesale. Selected browser layout keys are copied without copying chat state, secrets, trust decisions or arbitrary extension state. The approved pinned extensions are available in each workstation; this feature does not bypass the managed gallery or package-age policy.

This is application-level isolation on one trusted operator’s local broker. It is not isolation from the operator, not encrypted multi-tenant storage on the local machine, and not a production distributed identity deployment.

Reopening an existing running workstation now captures portable preferences from the same user's other running workstations and applies the merged profile. Stopped workstations are not woken. Missing saved extensions install in the background through the existing approved gallery; denied or unavailable extensions create an operation failure event. Browser-local layout state and extension-specific credentials remain outside the portable profile.

Older project-local theme/font overrides are backed up before being removed in favor of the account appearance profile. Project-specific editing rules are retained. Coding tools are instructed to write appearance preferences at user scope.

## Security Defaults and stale sign-in sessions

Entra error `530035` means Security Defaults blocked the request. Inspect the exact event in Entra **Sign-in logs**, including **Original transfer method**; a browser request can inherit a session originally established through device-code authentication. This occurred during pilot validation even though this application uses authorization code + PKCE. The failed event identified device-code flow, and choosing **Sign out and sign in with a different account → Use another account**, then entering the same account email, restored both the app and the Entra portal. Selecting the cached account tile continued to fail. This is a recovery procedure for that observed cause, not a universal fix for every `530035` event.

Refresh CLI access with `sh scripts/azure_pilot_az.sh login --tenant <tenant-id>` and complete its browser flow; avoid `--use-device-code`. Confirm refresh without printing credentials using `sh scripts/azure_pilot_az.sh account get-access-token --resource https://graph.microsoft.com --query expiresOn -o tsv`. Never copy browser tokens into CLI storage or disable tenant protections as an authentication workaround.

The local recovery chat retries history reads after a transient broker interruption and clears the read warning once history is available again. A failed or ambiguous message submission retains its separate warning and is never automatically resent.

Microsoft documents device-code blocking for new tenants starting July 1, 2026, and a 24-hour grace period before new-tenant Security Defaults enforcement. A policy can therefore start affecting an existing session without an application deployment. Check logs rather than assuming device registration, password expiry, or a missing Authenticator installation. Personal-account Authenticator registration and the resource tenant's Security info are separate contexts. For tenant-specific registration, use `https://mysignins.microsoft.com/security-info/?tenantId=<tenant-id>`; if no methods are offered, inspect the authentication-method policy rather than resetting existing credentials blindly.

References: [Microsoft Security Defaults](https://learn.microsoft.com/en-us/entra/fundamentals/security-defaults), [protocol tracking and Original transfer method](https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-authentication-flows#protocol-tracking), and [combined registration and external users](https://learn.microsoft.com/en-us/entra/identity/authentication/concept-registration-mfa-sspr-combined).

## Renewal and reconnect behavior

Sign-in requests `openid profile email offline_access`. Refresh tokens stay in the private, mode-0600 server session file; they never reach the editor, JavaScript, or repository. A session has an absolute eight-hour ceiling. Before the provider token expires, the broker serializes renewal for that session and validates the refreshed signature, issuer, audience, tenant, and unchanged user identity. Refresh-token rotation is persisted. Revocation requires interactive sign-in; transient upstream failures return a retryable 503 and do not discard the recoverable session. Older sessions without a refresh token require one new sign-in.

An API 401 no longer navigates the app away from an active editor. The reconnect notice opens Microsoft sign-in in a separate tab, then refreshes the CSRF token when the original tab regains focus. A different signed-in account reloads the app so cached data from the previous user is not reused. Recovery uses `prompt=login` to avoid silently reusing a failed SSO session. This does not disable Security Defaults, MFA, or Conditional Access; provider policy denials still require a valid Microsoft authentication flow.
