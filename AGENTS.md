# Working on Sandbox Lab

Prefer React and shadcn for frontend changes. Prefer polars to pandas and Plotly to matplotlib. Use uv for Python environments and packages.

Read README.md and docs/PROJECTS.md before changing workspace ownership or lifecycle. GUI workstations and headless projects keep separate files; Open in VS Code explicitly copies project source into the separate GUI home; returning changes to chat requires a reviewed source copy. Ordinary chat and documentation reads must not allocate a project.

Use the configured project engine deliberately: native Coder headless inference and in-workspace Ori/Pi have different credential boundaries. Do not weaken network, package-age or human-approval controls to make a test pass.

Keep `.local`, `.env`, credentials, conversations, workspace files and user-generated apps private. Never stage the entire filesystem or copy live state into source. Run `python3 scripts/repo_audit.py --staged` on the exact index before commits. Preserve existing data during migrations; back up before changing saved presentation.

Validate relevant changes with `.venv/bin/python -m pytest -q`, `npm run test:polling`, `npx tsc --noEmit`, and `npm run build`. See docs/VALIDATION.md for live checks and remaining portability/production limits. Refresh the curated docs and the standalone architecture report when behavior changes.
