# OpenAI External-Model Validation Report

## 1. Existing frozen primary validation (unchanged — reference only)

- 243 held-out proteins, 5 open-weight models, P1–P4, 14,580 calls, 60,585 claims
- Primary result: 355/7,431 = **4.78%** precision@10%-coverage; baseline 423/60,585 = **0.70%**
- Paired protein-bootstrap difference: **+4.08 points, 95% CI [+3.71, +4.47]**
- **Verified unchanged**: SHA-256 of `FROZEN_PROTOCOL.md`, `frozen_experiment_config.json`, `scripts/heldout_sample_250.json`, `scripts/heldout_draw_audit_log.json`, `scripts/llm_prompting_heldout.py`, and all 5 `heldout_results/*.jsonl` + manifest are identical before and after this experiment.
- **Verified**: the OpenAI model's predictions were never added to `n_models`; the 5-model score remains exactly as frozen.

## 2. New OpenAI external-model validation

**Model**: `gpt-5.5-2026-04-23`. **Calls**: 2,916 planned (243 × 3 namespaces × 4 prompts), **2,914 successful, 2 failed** (both same root cause, not retried — see Limitations).

### Critical finding first: 98.0% of successful calls returned empty output

2,855/2,914 successful calls produced zero visible GO claims — not because the model found nothing, but because **this reasoning model exhausted its entire 512-token completion budget on invisible internal reasoning** before producing visible output (confirmed via diagnostic probe: `finish_reason='length'`, `reasoning_tokens=512/512`; the same prompt succeeded at a 4,000-token budget). This means **only 100 distinct GO claims survived from the entire run**, and they are not a random sample — they are systematically the cases where the model's reasoning happened to be short. All analysis below is on this small, biased surviving set and should be read as exploratory, not confirmatory.

### A. OpenAI overall precision (all 100 claims, 40/243 proteins represented)

Total 100, correct 37, **precision 0.3700**. By namespace: MF 10/42=0.238, BP 3/6=0.500, CC 24/52=0.462. By organism: human 10/38=0.263, mouse 12/21=0.571, yeast 5/21=0.238, ecoli 10/20=0.500.

### B. Overlap with the frozen 5-model claim set

86/100 (86%) of OpenAI's claims already exist somewhere in the frozen pooled claim set; 14/100 (14%) are OpenAI-only and marked `not_in_frozen_claim_set` (precision among those: 6/14=0.429) — not scored against a frozen value, per instructions.

### Primary external-model analysis: precision vs. the PRE-EXISTING frozen score (86 overlapping claims)

| Frozen score | OpenAI claims | Correct | Precision |
|---|---|---|---|
| 2 | 5 | 0 | 0.000 |
| 3 | 5 | 1 | 0.200 |
| 4 | 3 | 1 | 0.333 |
| 5 | 4 | 0 | 0.000 |
| 6 | 1 | 1 | 1.000 |
| 7 | 12 | 5 | 0.417 |
| 8 | 4 | 0 | 0.000 |
| 9 | 14 | 5 | 0.357 |
| 10 | 3 | 0 | 0.000 |
| 11 | 2 | 2 | 1.000 |
| 12 | 8 | 4 | 0.500 |
| 13 | 10 | 3 | 0.300 |
| 14 | 15 | 9 | 0.600 |

Cumulative (score ≥ threshold): ≥14: 0.600 (n=15) → ≥9: 0.442 (n=52) → ≥2: 0.361 (n=86) — a noisy but generally decreasing cumulative curve as the threshold loosens, consistent in *direction* with the frozen primary pattern, on a far smaller and selection-biased sample.

### C. Agreement enrichment (binned — cleaner signal than the noisy per-score table)

| Frozen score bin | n | Correct | Precision |
|---|---|---|---|
| 2–4 | 13 | 2 | 0.154 |
| 5–8 | 21 | 6 | 0.286 |
| 9–11 | 19 | 7 | 0.368 |
| 12–14 | 33 | 16 | 0.485 |

**Monotonically increasing** — the same qualitative direction as the frozen primary result.

### D. Organism robustness (overlapping claims only)

human 10/35=0.286 (11 proteins), mouse 9/18=0.500 (8), yeast 4/16=0.250 (8), ecoli 8/17=0.471 (11). Small per-organism N; not over-interpreted.

### E. Namespace robustness (overlapping claims only)

MF 6/34=0.176, **BP 2/5=0.400 (n=5, BP sparse-ground-truth limitation applies, see `FROZEN_PROTOCOL.md` Sec. 17 — doubly unreliable here given the tiny n)**, CC 23/47=0.489.

### F. Protein-level analysis

Only 38/243 proteins contribute any evaluable overlapping claim. Protein-level bootstrap (B=2,000, seed=42) on the score≥9 bucket: point=0.442, 95% CI **[0.333, 0.569]** (N=32 proteins) — wide, as expected from this sample size.

## 3. Exploratory/secondary findings

- The agreement-enrichment bins (C) show the same monotonically-increasing direction as the frozen primary result, which is a mildly encouraging qualitative signal.
- 14% of OpenAI's claims are not in the frozen pool at all — too few to analyze meaningfully on their own (precision 0.429 on n=14).

## 4. Limitations (read before drawing any conclusion)

1. **This is not a clean test of the stated scientific question.** The question asked whether correctness increases with the pre-existing frozen score for an unseen model's predictions; the reasoning-token budget issue means we only observe this relationship on a non-random, budget-survivorship-biased 86-claim subsample across 38 proteins, not a full, fair sample of the model's actual predictions across all 2,916 attempted calls.
2. **Generation parameters differ from the frozen primary run in a disclosed way**: `temperature` could not be set to 0.0 (this model doesn't support it), and `max_completion_tokens` was kept at the frozen value of 512, which turned out to be far too small for this specific model's reasoning overhead — this was discovered only after the run completed and was not fixed mid-experiment, per instructions.
3. Sample sizes in every breakdown (organism, namespace, score bin) are small (often <20 claims), so none of these should be treated as statistically conclusive.
4. The 2 hard failures share the same root cause as the empty-response problem and were not retried with unchanged parameters (would fail again) or different parameters (would be adapting the experiment).

## 5. What this does and does not tell us

It does **not** overturn, confirm, or materially extend the frozen primary result, which remains the paper's primary finding, untouched. It **suggests** (very weakly, given the sample) that the same score-correctness direction may hold for an unseen reasoning model's rare successful outputs, but the experiment as executed cannot support a confident claim either way. The actionable finding is methodological: **this model needs a much larger completion-token budget to be fairly tested**, and re-running under a corrected, clearly-labeled configuration is a decision for you to make — not something I've done unilaterally.
