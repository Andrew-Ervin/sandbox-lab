# Sharing the repository safely

This repository contains implementation source, infrastructure examples, tests, reviewed extension assets/license, documentation and the explicitly requested standalone architecture report. It must not contain personal conversations, generated user applications/files, live credentials, databases or kubeconfigs.

`.gitignore` excludes `.local` (conversations, apps, artifacts, checkpoints, logs and Coder credentials), `.env*` except the blank `.env.example`, dependency caches, local Sites metadata, generated VSIX packages, private keys, Terraform state and local verification notes. `docs/VERIFICATION.md` is intentionally private because it contains local session identifiers. The architecture reference is the only prebuilt user-facing app intentionally shared; its operational examples are generic.

The report is [reports/architecture/architecture.html](../reports/architecture/architecture.html); the Azure handoff is [AZURE-IMPLEMENTATION.md](AZURE-IMPLEMENTATION.md). A fresh checkout has no personal chat history. `seed_architecture.py` optionally inserts the labeled reference conversation; it does not import old chats or other apps.

The [managed Pi design](MANAGED-PI-DESIGN.md) is included with the report. Diagnostic request payloads and smoke-session logs remain private under `.local`; the source archive includes neither them nor model/session credentials.

Before a commit:

```sh
python3 scripts/repo_audit.py
# Optional local pre-commit protection; versioned hook is supplied.
git config core.hooksPath .githooks
# Stage only the reviewed source files by explicit filename.
git add -- path/to/reviewed-file
python3 scripts/repo_audit.py --staged
git diff --cached --stat
git diff --cached
# Commit/push only after reviewing the destination and staged content.
```

The scanner reads exact index blobs with `--staged`, so an uncommitted cleanup cannot hide an already staged secret. It rejects force-added private paths, symlinks, oversized files and recognized credentials; when a local .env is available it also checks for its actual secret values without printing them. Findings show only path, line and rule. The GitHub workflow runs the index audit on pushes/PRs with a read-only token. Enable repository secret scanning/push protection, protected branches and required review through organization settings as well. A Git hook can be bypassed and CI runs after upload; neither replaces review before pushing.

To create a source-only transfer artifact without Git history or local state:

```sh
python3 scripts/repo_audit.py --archive .local/share/sandbox-lab-source.zip
```

The exporter writes only audited Git source candidates; it does not recursively zip the project directory or follow dependency symlinks. The archive itself stays ignored. Extract it into a new folder, run `git init` there if desired, and follow local setup. The scanner is a bounded high-confidence check, not full DLP or an audit of existing Git history. Review history separately before sharing an established repository. Never solve a warning by copying secrets into another tracked file or broadening an exclusion to hide it.

A credential previously pasted into a conversation remains in that conversation even if absent from Git. Rotate it before wider distribution, set the new key privately in `.env`, apply control-plane secrets, and restart the backend/gateway. No credential is embedded in the architecture HTML or source archive.

The requested destination for this handoff is a private repository named `sandbox-lab` under the user’s account. Preparation scripts themselves never create a repository, commit or push. Preserve the Pi Chat MIT license and documented upstream attribution; choose the project’s own distribution/license policy with the organization before publishing outside the team.
