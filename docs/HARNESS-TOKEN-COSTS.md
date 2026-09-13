# Harness token costs and Copilot comparison

## Pi versus Codex

Repricing the five successful sliding-window trials from [the harness benchmark](PARALLEL-HARNESS-COMPARISON.md) at the same standard Luna rates gives a 42.03% reduction in model cost for Pi. These are measured token counts multiplied by public rates, not invoices or a prediction for all workloads.

Rates checked September 13, 2026: $0.20 per million uncached input tokens, $0.02 per million cached input tokens, and $1.20 per million output tokens. Source: [OpenRouter Luna pricing](https://openrouter.ai/openai/gpt-5.6-luna-20260709). Provider/tier routing can change rates. Reasoning tokens are included in output and are not charged twice in this calculation.

| Across five tasks | Pi | Codex |
|---|---:|---:|
| Uncached input tokens | 17,573 | 98,757 |
| Cached input tokens | 134,799 | 959,331 |
| Output tokens | 42,767 | 50,248 |
| Uncached input cost | $0.003515 | $0.019751 |
| Cached input cost | $0.002696 | $0.019187 |
| Output cost | $0.051320 | $0.060298 |
| Total model cost | **$0.057531** | **$0.099236** |
| Mean cost per task | **$0.011506** | **$0.019847** |

Formula: `(uncached_input * 0.20 + cached_input * 0.02 + output * 1.20) / 1,000,000`.

The mean saving is $0.008341 per task, or approximately $8.34 per 1,000 similar tasks ($11.51 for Pi versus $19.85 for Codex). Use aggregate cost divided by five, rather than pricing separately selected median token counts. Most of Codex's extra input is cached, so the dollar saving is much smaller than the raw token reduction. Output accounts for about 89% of Pi's cost on this sample.

This excludes Azure compute, storage, registry, credit-purchase fees and tax. OpenRouter/model spending is controlled separately from the Azure-only $200 pilot ceiling. The broker retains separate model accounting without using it for Azure admission.

## Copilot method

Copilot CLI 1.0.83 uses the existing scoped OpenRouter gateway with `COPILOT_OFFLINE=true`, provider type `openai`, no GitHub authentication tokens, and Luna. The test uses `--yolo --reasoning-effort xhigh --output-format json`, five isolated 1 vCPU / 2 GiB environments, the same problem, and the same independent oracle. YOLO applies only to these disposable CLI invocations; Azure egress and package-age controls remain active. It is not a default workstation setting.

GitHub documents [local BYOK and offline mode](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models) and [YOLO permissions](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/allowing-tools). Offline here means no GitHub service dependency; model requests still reach OpenRouter through the broker.

An initial setup attempt was interrupted to align reasoning effort. A subsequent batch hit the old combined Azure/model reservation cutoff; its incomplete outcomes are excluded from performance comparison. The measured comparison uses fresh environments after separating the budgets. No model or provider was substituted to make the test pass.

## Copilot results

All five fresh runs completed successfully and passed the independent 780-case oracle, boundary tests and 200,000-element check.

| Run | Setup seconds | Agent seconds | Total with verification seconds | Passed |
|---|---:|---:|---:|---|
| 1 | 40.2 | 54.0 | 95.5 | Yes |
| 2 | 35.6 | 130.3 | 167.2 | Yes |
| 3 | 40.4 | 119.7 | 161.6 | Yes |
| 4 | 35.4 | 89.3 | 126.0 | Yes |
| 5 | 40.5 | 69.4 | 111.3 | Yes |

Median agent time was 89.3 seconds; median total was 126.0 seconds. The earlier Pi and Codex median agent times were 114.6 and 140.2 seconds. These ordered batches are a small sample, not a controlled latency ranking; setup also differs because Copilot was configured in a later batch.

Copilot's JSON event stream did not expose input/output/cache usage. Its 40 unique generation identifiers were queried through the [OpenRouter generation endpoint](https://openrouter.ai/docs/api/api-reference/generations/get-generation), but the returned records had zero token/cost counters and missing finish metadata despite successful code generation. These counters are treated as unavailable, not as evidence of free inference. A reliable Copilot cost comparison cannot be calculated from this run. All five disposable environments were cleaned up after testing.
