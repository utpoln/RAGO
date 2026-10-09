# Pilot Cost/Quality Optimization Report

**No scientific claims are made in this report. This pilot tests
configuration, completeness, and cost only. The archived previous
full-scale run and the frozen primary experiment were not modified.**

## 1. Configurations tested
Exactly 2, as specified:
- **A**: reasoning_effort=low, max_completion_tokens=4000, Batch API
- **B**: reasoning_effort=medium, max_completion_tokens=4000, Batch API

## 2. Exact model ID
`gpt-5.5-2026-04-23` — confirmed in every returned response body, unchanged from the original run.

## 3. Exact reasoning setting
`low` (Config A) and `medium` (Config B) — both accepted by the API without error, verified on a real scientific prompt before committing to the 48-call batches.

## 4. Exact completion-token setting
`max_completion_tokens=4000` for both configurations.

## 5. Batch status
**Supported.** A 2-request feasibility batch was run first and completed successfully (~3 minutes) before committing the real pilot batches. Both 48-call pilot batches (A and B) also completed successfully, 48/48 requests each.

## 6. Prompt caching status
**Did not engage in either configuration.** `cached_tokens=0` across all 96 pilot calls. Root cause: mean prompt length was 265 tokens — far below OpenAI's ~1,024-token minimum for caching to activate at all, regardless of how much identical structure is repeated across calls. This is a property of the (correctly unmodified) scientific prompts, not a configuration error.

## 7. Number of pilot calls
96 total (48 per configuration).

## 8. Usable-response rate
- Config A: 48/48 (100%)
- Config B: 47/48 (97.9%)

## 9. Empty-output rate
- Config A: 0/48 (0%)
- Config B: 1/48 (2.1%)

## 10. Truncation rate
- Config A: 0/48 (0%)
- Config B: 1/48 (2.1%) — this one call hit `finish_reason=length` with `reasoning_tokens=4000` (the entire budget) and produced no visible output, even at the 4,000-token ceiling.

## 11. Average/median reasoning tokens
- Config A: mean 454.3, median 496 (range 146–980)
- Config B: mean 1,172.3, median 512 (range 444–4,000)

## 12. Average/median output tokens (includes reasoning)
- Config A: mean 501.0
- Config B: mean 1,225.5

## 13. Average input and cached-input tokens
- Both configs: mean input 265.2 tokens/call; cached input 0 (caching never engaged)

## 14. Actual pilot cost (48 calls each, standard non-Batch rates: $5/M input, $0.50/M cached input, $30/M output)
- Config A: **$0.7851**
- Config B: **$1.8283**
(If a 50% Batch discount applies — reported by third-party sources but not independently verified against this session's actual billing — A: $0.39, B: $0.91.)

## 15. Projected cost for all 2,916 calls (scaled from observed averages)
| | Standard rate | If Batch discount applies (unverified) | Conservative (max observed reasoning tokens) |
|---|---|---|---|
| Config A | $47.70 | $23.85 | $93.62 |
| Config B | $111.07 | $55.54 | $358.42 |

## 16. Is the configuration adequate for production?

- **Configuration A (low)**: Yes — 0% truncation, 0% empty output, 100% GO-bearing responses across all 48 calls, comfortably within the 4,000-token budget (max observed reasoning: 980).
- **Configuration B (medium)**: Partially — 97.9% usable, but one call (2.1%) exhausted the full 4,000-token budget on reasoning alone and returned nothing. This is the exact "4,000 tokens still inadequate" stop condition, triggered at a low rate rather than "a large fraction." Reported, not resolved by raising the budget further.

## 17. Recommended configuration for the full run

**Configuration A: reasoning_effort=low, max_completion_tokens=4000, Batch API, seed=42.**

Rationale: zero completeness failures in the pilot (vs. a real, non-zero failure rate for medium), roughly 2.3× cheaper (~$48 vs. ~$111 projected for the full 2,916 calls at standard rates), and still produces non-trivial GO-term output (mean 3.27 terms/call, matching Config B's mean exactly — reasoning_effort did not measurably change output richness in this pilot, only cost and failure rate). This recommendation is based solely on completeness/reproducibility/cost criteria, not on GO-prediction precision, per the pilot's scope restriction.

---

**STOPPING HERE. The full 2,916-call OpenAI experiment has not been started. Awaiting approval before proceeding.**
