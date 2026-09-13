# Parallel coding harness benchmark: sliding-window absolute deviation

2026-09-13. Requested comparison: five isolated environments per harness, run concurrently within each harness batch. Batches are ordered Pi, Codex, Claude Code, so this is not a randomized provider/cache comparison. All use Luna through Ori, 1 vCPU / 2 GiB and the same custom image without launching the editor. This exercises workspace CLI harnesses, not a replacement production headless engine.

## Problem and verification

Implement `sliding_cost(nums, k)`: for each sliding window, return the minimum sum of absolute deviations from an integer center. Handle duplicates, negative/large integers, invalid window sizes and empty input; preserve input. Require O(n log n) time and O(n) or better memory. Each solution is checked with 780 seeded brute-force cases, boundary cases, and a 200,000-element case with independently known costs. Agents also write and run their own tests.

## Completed measurements

Times are wall-clock seconds observed by the broker; agent time includes tool execution and result polling. Input below includes cached input. Cached input is a subset, not additional tokens. Reasoning is included in output where the client reports it; it must not be added again. Usage is summed only from final assistant-message events, not intermediate streaming updates.

| Pi run | Setup | Agent | Total + verification | Input incl. cache | Cached input | Output incl. reasoning | Total tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 70.6 | 74.2 | 148.6 | 16,803 | 14,425 | 5,155 | 21,958 |
| 2 | 70.6 | 79.2 | 152.2 | 22,501 | 19,607 | 5,482 | 27,983 |
| 3 | 70.6 | 144.9 | 216.9 | 25,673 | 22,213 | 10,832 | 36,505 |
| 4 | 70.6 | 230.9 | 302.9 | 69,954 | 63,609 | 14,056 | 84,010 |
| 5 | 70.6 | 114.6 | 186.7 | 17,441 | 14,945 | 7,242 | 24,683 |

All five Pi solutions passed. Median agent time was 114.6 seconds; median total token usage was 27,983. The large verification case took 0.53–2.18 seconds. The spread is mostly agent reasoning/tool behavior, not insufficient CPU for the finished algorithm.

## Incomplete comparison and infrastructure findings

The first parallel attempt hit HTTP 429 because the broker polled every result file every 0.4 seconds. Those measurements are excluded from algorithm comparisons. The runtime now backs result polling off to five seconds and retries only read observations, never command submission. Completed-result cleanup failure is logged without discarding the result. The five successful Pi runs above use that fix.

The following Codex batch started five environments, but Azure credential refresh failed before result retrieval completed. These are unknown coding outcomes, not algorithm failures. Final token usage and fair agent timing are unavailable. Claude's batch could not allocate environments after the same access failure. Do not compare those failed setup/retrieval durations with Pi's successful runs. The browser also reported an Entra resource-access denial after successful sign-in; account access must be restored before completing the comparison.

The failed disposable test environments require reconciliation and deletion once Azure access returns. The configured ten-minute platform auto-suspend remains in place, but suspension/deletion was not verified after the credential failure. No authentication or network policies were weakened to finish the test.

This is a small benchmark on one problem. It provides no defensible Pi/Codex/Claude ranking until the other batches complete. Provider billing is separate from client-reported token counts and conservative broker reservations.
