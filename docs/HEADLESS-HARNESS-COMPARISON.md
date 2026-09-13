# Headless CLI comparison

The pilot compared Pi, Codex and Claude Code through Ori using the same configured Luna model and xhigh reasoning, 1 vCPU / 2 GiB, and a fresh disposable workspace for each run. No editor was opened. These used the existing developer-image capability route for CLI inference, not the production headless engine, which keeps inference in the broker. That production engine was not replaced by this experiment.

The task was weighted job scheduling with reconstruction: return maximum profit and original job indices in chronological order, support touching intervals, do not mutate input, and handle 100,000 jobs in O(n log n) time and O(n) memory without linear recursion. The independent checker covered 134 fixed/randomized cases against brute force and a 100,000-job case. All six permission-ready samples passed.

| Harness | Agent seconds, two runs | Fresh setup seconds | Total including independent verification | 100,000-job execution |
|---|---|---|---|---|
| Pi / Ori | 55.97, 51.53 | 26.77, 27.02 | 83.47, 79.28 s | 0.098, 0.094 s |
| Codex / Ori | 65.08, 62.47 | 29.03, 27.23 | 95.10, 90.44 s | 0.094, 0.096 s |
| Claude Code / Ori | 29.15, 47.96 | 27.75, 27.23 | 57.62, 75.91 s | 0.125, 0.097 s |

Setup includes configuring the CLI tools, not just Azure allocation. Reuse avoids much of that phase. Pi used five and seven tool calls. Codex produced an iterative DP solution and a separate test file in both runs. These are small samples, not statistically meaningful percentiles or a ranking across codebases.

Claude's initial unattended configuration was not permission-ready: one attempt timed out after 240 seconds without a solution; another returned an explicit request for permission to write and execute Python. Those attempts are excluded from the timing comparison above but are part of the reliability finding. The subsequent test invocation explicitly allowed reads, current-directory writes/edits and Python commands already requested by the operator. Other approvals were retained; network and package policy were unchanged. Agent/Task and web tools were disabled in those Claude samples to avoid helper-model delegation and keep the experiment on Luna. No production permission settings were changed. Claude also emitted a model-catalog warning; a completed generated solution and independent tests, rather than exit status alone, determined success.

For this task all three solved the problem comfortably within the compute allocation. Claude was quickest after scoped permission setup, Pi was consistent and already fits the application's agent workflow, and Codex was modestly slower with equally correct artifacts. Keep quick numerical work in the Python pool and retain the current production headless engine pending a broader multi-problem comparison. All benchmark-owned sandbox compute was removed; raw transcripts and generated code remain private.

A harder five-environment parallel trial, including token accounting and its access-policy blocker, is recorded in [parallel comparison](PARALLEL-HARNESS-COMPARISON.md).
