# Pilot Cost/Quality Optimization Protocol

**Purpose: configuration and cost estimation only. No scientific claims.
The previous failed full-scale run (`../raw/gpt-5.5-2026-04-23.jsonl`,
512-token budget, 98% empty output) remains archived, untouched, and is
not treated as evidence of anything beyond its own documented failure
mode.**

## Model
`gpt-5.5-2026-04-23` (unchanged from the original run — not switched).

## Pilot sample
4 proteins, 1 per organism (human, mouse, yeast, E. coli), selected via
`random.Random(42).shuffle()` on sorted per-organism accession lists from
the frozen `heldout_sample_250.json`, first element of each shuffle taken.
Selected **before** any OpenAI call existed for this pilot — not based on
prior OpenAI results. See `pilot_sample.json` for the exact accessions:
human=Q86YC3, mouse=P62301, yeast=P07347, ecoli=P76347.

## Scientific task (unchanged)
Exact namespace-specific P1–P4 prompts, imported directly from
`../../scripts/llm_prompting_heldout.py::build_prompts()` — not retyped,
not restructured, not combined across namespaces, few-shot examples
unchanged. 4 proteins × 3 namespaces × 4 prompts = 48 calls per
configuration.

## Configurations tested (exactly 2, as specified)

| | A | B |
|---|---|---|
| reasoning_effort | low | medium |
| max_completion_tokens | 4000 | 4000 |
| API | Batch | Batch |
| seed | 42 | 42 |

`high`/`xhigh` were not tested — not required by the API and A/B did not
reveal a quality/completeness problem severe enough to warrant it (see
results).

## Batch API feasibility check (done before committing the 48×2 pilot)
A tiny 2-request feasibility batch was submitted and polled to completion
first (`batch_6ac74f797464819082f22045cbcfb961`, completed in ~3 minutes,
model field confirmed as `gpt-5.5-2026-04-23`, reasoning_effort="low"
accepted). Only after this succeeded were the real 48-call pilot batches
submitted.

## Reasoning-effort parameter check (done before committing the pilot)
Learning from the previous run's mistake (probes used only trivial
prompts, which didn't reveal the reasoning-budget problem), `reasoning_effort`
was tested on **both** a trivial prompt and a real scientific P1 prompt at
`max_completion_tokens=4000` before any batch was submitted. Both `low`
and `medium` succeeded on the real prompt in this preliminary check.

## No-leakage commitments honored
- Pilot proteins were not selected based on any OpenAI result.
- Configuration was not tuned against GO-prediction precision — only
  against completeness/reproducibility/cost/absence-of-API-failure (Sec.
  10 of the original instructions).
- No change was made to the frozen five-model framework, prompts, GO
  ontology, or held-out cohort (beyond selecting this fixed 4-protein
  pilot subset).
- The OpenAI model was not added to `n_models`.

## Stop conditions encountered
**Stop condition 4 (partially triggered)**: Configuration B had 1/48 calls
(2.1%) reach `finish_reason=length` with `reasoning_tokens=4000` (the full
budget) and empty visible output. This is not "a large fraction," but it
is a nonzero inadequacy at the *medium* reasoning-effort setting even at
4,000 tokens, and is reported rather than resolved by raising the budget
further. Configuration A had zero such incidents.

## Pricing
GPT-5.5 standard rates: $5.00/M input, $0.50/M cached input, $30.00/M
output (confirmed via WebSearch against multiple independent third-party
pricing aggregators; OpenAI's own pricing page returned HTTP 403 to direct
fetch in this session). Batch API is reported by the same sources to cut
all rates by 50%, but this was **not** independently verified against
actual billing data — the Batch object's `usage` field returns token
counts, not dollar amounts.
