# Parallel coding harness benchmark: sliding-window absolute deviation

2026-09-13. Requested comparison: five isolated environments per harness, run concurrently within each harness batch. Batches are ordered Pi, Codex, Claude Code, so this is not a randomized provider/cache comparison. All use Luna through Ori, 1 vCPU / 2 GiB and the same custom image without launching the editor. This exercises workspace CLI harnesses, not a replacement production headless engine.

## Problem and verification

Implement `sliding_cost(nums, k)`: for each sliding window, return the minimum sum of absolute deviations from an integer center. Handle duplicates, negative/large integers, invalid window sizes and empty input; preserve input. Require O(n log n) time and O(n) or better memory. Each solution is checked with 780 seeded brute-force cases, boundary cases, and a 200,000-element case with independently known costs. Agents also write and run their own tests.


## Completed measurements

Times are wall-clock seconds observed by the broker. Setup includes sandbox creation and harness configuration, not just Azure startup. Agent time includes tool execution and result polling. Five environments run concurrently within each harness batch. Input includes cached input; cached tokens are a subset, not additional tokens. Reasoning is included in output where reported. Client usage is not a billing export.

### Pi

| Run | Setup | Agent | Total + verification | Input incl. cache | Cached input | Output | Passed |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 70.6 | 74.2 | 148.6 | 16,803 | 14,425 | 5,155 | Yes |
| 2 | 70.6 | 79.2 | 152.2 | 22,501 | 19,607 | 5,482 | Yes |
| 3 | 70.6 | 144.9 | 216.9 | 25,673 | 22,213 | 10,832 | Yes |
| 4 | 70.6 | 230.9 | 302.9 | 69,954 | 63,609 | 14,056 | Yes |
| 5 | 70.6 | 114.6 | 186.7 | 17,441 | 14,945 | 7,242 | Yes |

5/5 passed. Median agent time: 114.6 seconds. Median total tokens: 27,983.

### Codex

| Run | Setup | Agent | Total + verification | Input incl. cache | Cached input | Output | Passed |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 71.1 | 140.2 | 212.6 | 237,178 | 218,780 | 11,312 | Yes |
| 2 | 71.1 | 89.7 | 163.1 | 146,188 | 135,201 | 6,747 | Yes |
| 3 | 71.1 | 140.2 | 212.6 | 172,223 | 157,878 | 11,068 | Yes |
| 4 | 77.1 | 125.3 | 203.8 | 239,379 | 211,639 | 9,852 | Yes |
| 5 | 71.2 | 150.2 | 222.8 | 263,120 | 235,833 | 11,269 | Yes |

5/5 passed. Median agent time: 140.2 seconds. Median total tokens: 248,490.

### Claude

| Run | Setup | Agent | Total + verification | Input incl. cache | Cached input | Output | Passed |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 66.2 | 195.7 | 263.1 | 812,738 | 792,781 | 10,336 | Yes |
| 2 | 66.3 | 326.9 | 394.5 | 400,291 | 389,425 | 39,119 | Yes |
| 3 | 66.1 | 134.9 | 202.4 | 387,953 | 366,567 | 7,348 | Yes |
| 4 | 66.1 | 69.3 | 136.7 | 101,226 | 97,686 | 3,801 | Yes |
| 5 | 66.1 | 130.6 | 198.1 | 308,249 | 287,817 | 7,052 | Yes |

5/5 passed. Median agent time: 134.9 seconds. Median total tokens: 395,301.

## Interpretation and infrastructure findings

This is a small, ordered benchmark on one problem with one model. Harness system prompts, available tools and provider cache behavior differ; these are part of the observed harness overhead. It does not establish a general model or harness ranking. Pi usage sums only final assistant message events; Codex uses completed-turn usage; Claude uses its final result usage. Claude input includes cache-creation tokens as well as cache reads and uncached input; the cached column shows reads only. Cached input must be priced separately from uncached input, and harness-reported dollar estimates are not authoritative provider billing.

For this workload Pi had the lowest median time and least context usage, Codex had the narrowest timing range, and Claude had the widest range. All finished algorithms fit comfortably in 1 vCPU / 2 GiB: the large verification case took 0.51–2.18 seconds. Harness reasoning and tool activity dominate total time. The 66–77 second setup includes provisioning and configuring all harness wrappers; it is not a measurement of minimum Azure sandbox launch latency. A preconfigured warm environment could remove repeated setup from user-visible latency, but these results alone do not quantify that improvement. The production headless engine is unchanged.

The first attempt hit HTTP 429 because result files were polled every 0.4 seconds. Those measurements are excluded. The runtime now backs result polling off to five seconds and retries only observations, never command submission. Completed-result cleanup failure is logged without discarding the result. All reported runs use that fix.

An earlier Codex batch lost Azure authentication before results could be retrieved; those outcomes are unknown and excluded. Entra recorded the browser session's Original transfer method as Device code flow, blocked by Security Defaults. Fresh explicit account sign-in and normal browser-based CLI login restored access without changing security policy. The abandoned disposable test environments were deleted before rerunning Codex and Claude.

All fifteen reported test environments were deleted after completion. The benchmark ledger has no remaining undeleted test mappings. No user workspace was deleted by benchmark cleanup.
