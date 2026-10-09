# RAGO Reliability Framework — Frozen Held-Out Validation Protocol

**Status: PRE-REGISTERED. Frozen before any held-out LLM call.**
**Date frozen:** 2026-10-05 (prior to sample draw completion / first LLM call)

This document is the single source of truth for the held-out confirmatory
experiment. Nothing in Sections 1–8 may be changed after held-out results
are examined. If the held-out result is poor, that is reported as a
finding — the framework is not retuned and re-run against this same set.

---

## 1. Primary Claim

> Does the frozen reliability framework — built and calibrated exclusively
> on PROBE's 1,000-protein development set — generalize to previously
> unseen proteins?

## 2. Primary Statistical Unit

**The protein.** GO-term claims generated from the same protein (across
namespaces, models, and prompts) are correlated, not independent. All
confidence intervals for the primary claim resample **proteins** with
replacement; claims never get resampled independently of the protein that
produced them. The number of claims a protein happens to produce (~60
per protein at the frozen call budget, more in earlier exploratory dev-set
analyses) is not treated as additional independent sample size. **The
reported statistical unit throughout is N=243 proteins -- never an
"effective N" inflated by claim counts.**

## 3. Reliability Score Definition

For a candidate claim `(accession, namespace, go_id)`:

```
n_models               = number of the 5 frozen models (Sec. 6) that
                          predicted this exact go_id for this
                          (accession, namespace), pooling across P1–P4.
                          Range: 0–5.

max_prompt_consistency = max over the 5 models of (number of the 4
                          prompts, out of P1/P2/P3/P4, under which that
                          specific model predicted this exact go_id).
                          Range: 0–4.

rago_support            = 1 if go_id appears in the BLAST-retrieved
                          candidate list for this (accession, namespace)
                          per the frozen RAGO retrieval pipeline
                          (Sec. 6); else 0.

combined_score          = n_models + max_prompt_consistency + 5*rago_support
                          Range: 0–14.
```

None of these three components reads the target protein's own ground
truth. `n_models`/`max_prompt_consistency` depend only on cross-model and
cross-prompt agreement about what was *predicted*; `rago_support` depends
only on BLAST homology to a disjoint pool of other proteins. Ground truth
is used **only** downstream, to label a claim correct/incorrect for
evaluation — never as an input to the score. (Verified by direct code
inspection: see Section 12, item 1.)

**Ties:** claims sharing the same `combined_score` within a protein are
not arbitrarily broken; they are carried together as a tied bucket
through the coverage computation (Sec. 4).

## 4. How 10%-Coverage Is Determined

Within one protein-cluster-bootstrap replicate:
1. Pool **all** claims (all 3 namespaces, all 5 models, all 4 prompts)
   belonging to the resampled set of proteins.
2. Sort pooled claims by `combined_score` descending.
3. `target_n = total_pooled_claims * 0.10` (resampling draws from the 243
   held-out proteins -- see Section 10 for the final N and organism
   allocation).
4. Walk from the highest score downward, accumulating whole score-buckets
   (never splitting a tied bucket) until `cumulative_n >= target_n`.
   (Actual coverage may slightly overshoot 10% when a large tied bucket
   straddles the cutoff — this is accepted and documented, not corrected.)
5. `precision = correct_claims_in_top_set / total_claims_in_top_set`.

## 5. What Counts As Correct

A claim is correct iff `go_id` appears in that protein's own
experimentally-annotated GO set for that namespace, using the same
evidence-code filter as PROBE/ADAPT/RAGO throughout: `{IDA, IMP, IPI,
IGI, IEP, EXP, HDA, HMP, HGI, HEP}`. Ground truth for held-out proteins
is taken from their UniProt record **at the time of the held-out draw**
(the same snapshot used to determine qualification), not from any later
re-query.

## 6. Frozen Components

| Component | Frozen value |
|---|---|
| Model identities | `mistral-large:123b`, `qwen2.5:72b`, `google/gemma-4-31b`, `mixtral:8x7b`, `mistral:7b` (MindRouter identifiers) |
| Model selection rule | Ranks {1,3,5,7,9} of PROBE's published Table 5 leaderboard — a mechanical rule defined only from already-published PROBE numbers, verified via leave-one-out to show no single model is load-bearing |
| Prompts | `P1_zeroshot`, `P2_constrained`, `P3_fewshot`, `P4_cot` — exact wording from PROBE's `llm_prompting.py::build_prompts()`, unmodified. **P5 excluded from primary analysis** (see Sec. 7 rationale) |
| Scoring formula | As in Section 3 |
| BLAST database | `RAGO/pool_blastdb`, built via `makeblastdb` (BLAST+ 2.17.0) from `RAGO/pool_proteins.fasta` = ADAPT's 25,460-protein training pool, excludes PROBE's 1,000 and (by construction) all held-out accessions |
| BLAST parameters | `blastp`, e-value=1e-5, max_target_seqs=50, top_k_hits=10 (hits pooled per query), top_k_terms=15 (candidate list size per namespace) |
| GO ontology | `go-basic.obo`, release 2026-03-25, 48,321 terms (corrected bookkeeping figure, direct `[Term]` count; file itself unchanged -- see Sec. 15) |
| Evidence-code rule | Experimental = `{IDA, IMP, IPI, IGI, IEP, EXP, HDA, HMP, HGI, HEP}`; all other evidence codes (incl. IEA) excluded |
| Primary endpoint | Precision @ 10%-coverage (Sec. 4) |
| Secondary endpoints | Per-protein top-1 precision; precision @ {1%, 5%, 20%, 50%} coverage; per-organism breakdown; per-namespace breakdown; calibration; dev-vs-held-out comparison |

## 7. Why P5 Is Excluded From the Primary Analysis

None of the three score components use P5 data: `n_models` and
`max_prompt_consistency` are computed purely from P1–P4; `rago_support`
is a pure BLAST-retrieval feature requiring zero LLM calls. Omitting P5
removes no information the frozen framework uses and does not change the
primary claim. A small separate P5 analysis (e.g. to reproduce PROBE's
own prompt-format comparison on held-out data) may be run later as an
independent, clearly-labeled secondary study — it must not be merged
into the primary reliability-generalization claim or used to retune it.

## 8. Success / Failure Criterion (corrected — no post-hoc magnitude threshold)

**Primary hypothesis:** `precision@10%-coverage > baseline` (the
held-out set's own 100%-coverage, no-selection precision), i.e. the
frozen reliability score provides genuine separation on unseen proteins.

**Test:** 95% protein-bootstrap CI (Sec. 9) for
`(precision@10% − baseline)`, computed on the held-out set.
- CI excludes zero → hypothesis **supported**.
- CI includes zero → hypothesis **not supported** on this held-out set.

This is evaluated exactly once. No retuning, no re-running the same
held-out set under a modified score. A poor result is reported as a
finding.

Separately, and explicitly **not** a pass/fail gate: the held-out point
estimate and CI will be reported alongside the pre-registered dev-set
reference (0.0595, 95% CI [0.0563, 0.0631], computed on PROBE's full
1,000-protein development set under the identical frozen formula) and
the magnitude of any change will be described — without an a priori
"acceptable degradation" threshold, since no such threshold was
specified before seeing any held-out data.

## 9. Protein-Level Bootstrap CI Procedure

- B ≥ 1,000 replicates (real analysis; B=1,000 minimum, higher preferred
  if compute allows).
- Each replicate: resample N_heldout=243 proteins **with replacement**
  from the 243 held-out proteins (a protein drawn twice contributes its
  full claim set twice).
- Pool all claims from the resampled proteins; compute
  precision-at-10%-coverage (Sec. 4) on the pooled pseudo-sample.
- 95% CI = 2.5th / 97.5th percentiles of the B replicate values.
- Seed = 42 for the bootstrap RNG.

## 10. Final Held-Out Sample (Design A — approved, no redraw)

**N = 243.** Organism allocation: human 63, mouse 63, yeast 62, ecoli 55.
Zebrafish excluded (0% empirical yield; eligible pool already exhausted
by PROBE+ADAPT). This is the natural, unmanipulated output of the frozen
draw procedure (seed=42 shuffle, sequential qualification check, full
audit log in `heldout_draw_audit_log.json`) — **not redrawn, substituted,
topped up, or rebalanced** after discovering E. coli's pool exhaustion
(target was 62; entire fresh E. coli pool of 2,495 accessions was
exhaustively checked; only 55 qualified).

Eligibility criterion (unchanged, not retuned after observing the
annotation-distribution shift): ≥3 total experimental GO terms (any
namespace, pooled) AND non-empty UniProt FUNCTION comment — identical to
the rule used to build the ADAPT pool being excluded. Excluded
populations: every accession in PROBE's 1,000 ∪ ADAPT's 25,460 (verified
zero overlap, Sec. 13).

Primary claim is **Q1** (generalization to genuinely new proteins drawn
from the frozen eligibility population), not Q2 (generalization to a
PROBE-distribution-matched population). Distribution matching was
evaluated and explicitly rejected: infeasible to apply consistently
across all 4 organisms (yeast/ecoli pools too exhausted for stratification
to matter), and not required for Q1.

**Full sampled accession list (sorted, by organism):**

**human** (n=63): A0JLT2, O15231, O15539, O43316, O60393, O60516, O75882,
P01848, P06126, P0CG12, P0DPB6, P11678, P17509, P24855, P25092, P31513,
P33402, P49788, P51825, P54750, Q0P5N6, Q10981, Q14CB8, Q16816, Q2M1V0,
Q494V2, Q4G0U5, Q53ET0, Q5JTH9, Q5T4T6, Q6NVY1, Q6ZN30, Q6ZTW0, Q7Z6A9,
Q7Z7K0, Q86UW9, Q86YC3, Q8IVH2, Q8IZF2, Q8N5B7, Q8N5C6, Q8TBB1, Q8WVF2,
Q8WXX7, Q969S6, Q96B77, Q96BY7, Q96KN4, Q96KR4, Q99705, Q9BPX5, Q9BW61,
Q9BWN1, Q9BWU1, Q9NUU6, Q9NVU0, Q9NYZ3, Q9UDY6, Q9UGY1, Q9ULT8, Q9UNY4,
Q9Y3R0, Q9Y576

**mouse** (n=63): A2ATU0, J3QMY9, O08715, O35250, O35690, P03940, P46978,
P51661, P53612, P62301, P97467, Q04646, Q14AW5, Q3MI48, Q3T9E4, Q3UN02,
Q5FWI3, Q5M8M9, Q5PR68, Q5Y5T1, Q69ZR9, Q6IQY5, Q6Y4S4, Q7TRX1, Q7TSF1,
Q80T41, Q80TE7, Q8BMW7, Q8BPM0, Q8BUB4, Q8BW94, Q8BXA6, Q8BZH1, Q8C0T9,
Q8HWB0, Q8K4H1, Q8N7N5, Q8R316, Q8R317, Q91VB4, Q922Q1, Q922W5, Q925I7,
Q99LS3, Q99ML8, Q9CQT9, Q9CR25, Q9CWR7, Q9D2V8, Q9D826, Q9DA01, Q9DAG9,
Q9DAU7, Q9DCR4, Q9EQ20, Q9ES70, Q9JK45, Q9JMG3, Q9R061, Q9R1P0, Q9R1T2,
Q9WVM8, V9GX91

**yeast** (n=62): P00812, P07347, P0C0W9, P0CX31, P0CX33, P0CX43, P0CX44,
P0CX52, P10664, P23248, P25351, P25377, P25378, P25619, P29453, P32843,
P34228, P35497, P36154, P38069, P38070, P38197, P38289, P38688, P38732,
P38791, P39548, P39994, P40467, P41902, P43597, P46982, P47015, P47087,
P47976, P48164, P48564, P49626, P53075, P53200, P53289, P53873, P53878,
P53971, P54003, Q03323, Q03702, Q03942, Q05778, Q06011, Q06098, Q06116,
Q06162, Q06668, Q07541, Q08689, Q12006, Q12152, Q12155, Q12516, Q3E757,
Q3E7Y3

**ecoli** (n=55): P04335, P06993, P07464, P07822, P08839, P0A6J1, P0A790,
P0A8X0, P0AC55, P0ACY3, P0ADN0, P0ADY1, P0C8J6, P0DKB3, P0DP90, P13016,
P14565, P15028, P15038, P17443, P18392, P19636, P23883, P24173, P24205,
P27241, P27243, P29208, P30178, P31551, P33221, P38393, P45508, P46854,
P52073, P52645, P64506, P64559, P68191, P69222, P75713, P75782, P76145,
P76234, P76346, P76347, P76458, P76459, P76472, P77215, P77306, P77319,
P77510, P77748, Q06065

## 11. Call Budget

`243 proteins x 3 namespaces x 5 models x 4 prompts = 14,580 calls`
(revised down from the original 15,000 at N=250). Calls per protein = 60.
Calls per model = 2,916. Calls per prompt = 3,645. Calls per organism:
human 3,780; mouse 3,780; yeast 3,720; ecoli 3,300.

## 12. Missing / Invalid Output Handling

A call is recorded with `success: false` and an `error` string if the
MindRouter API call raises an exception (timeout, connection error,
non-2xx response, etc.) — exactly matching PROBE's own `call_model()`
error path in `llm_prompting.py`. `response` is left empty (`""`) on
failure. On any subsequent run of the same script, `load_completed()`
re-derives the set of already-*successful* `(accession, namespace,
prompt_id)` keys from the output file and skips only those — failed
calls are automatically retried on re-run, never silently dropped or
imputed. No model/prompt/protein/namespace combination is skipped
outright; every combination is attempted exactly once per (re)run cycle
until it succeeds or the run is manually stopped.

## 13. Deduplication Rules

Within a single model response, GO IDs are extracted via regex
(`GO:\d{7}`) into a **Python `set`** before being used anywhere
downstream — a model that lists the same GO ID twice in one response
contributes exactly one claim, not two. Across prompts, `n_models` and
`max_prompt_consistency` are computed from `(model, prompt)` pairs stored
in a `set` per `(accession, namespace, go_id)` — repeat predictions of
the same term by the same model under the same prompt cannot inflate the
score. At the sampling level, the held-out accession list itself is
verified duplicate-free (Sec. 15, item 3).

## 14. Output File Naming and Logging Scheme

One JSONL file per model, matching PROBE's own convention exactly:
`heldout_results/{model_slug}.jsonl`, where `model_slug` replaces `/`
and `:` with `_`/`-` (e.g. `mistral-large:123b` -> `mistral-large-123b`,
`google/gemma-4-31b` -> `google_gemma-4-31b`). Each line is one JSON
record: `accession, gene_name, organism, namespace, prompt_id,
prompt_text, model, response, success, error, usage, timestamp`. Files
are append-only and resumable (Sec. 12). The complete held-out draw audit
trail (`heldout_sample_250.json`, `heldout_draw_audit_log.json`) and this
frozen protocol file are retained unmodified as the permanent record of
the pre-registered design.

## 15. Preflight Audit (run before any LLM call; see chat response for
the full run log)

1. File existence — all required frozen inputs present (BLAST db, GO
   OBO, PROBE/ADAPT datasets, held-out sample + audit log). **Three
   required artifacts do not yet exist and must be created (zero LLM
   cost) before calls begin:** `heldout_query_proteins.fasta` (raw
   sequences, needed for BLAST retrieval only — not needed for P1–P4
   generation calls), `heldout_rag_candidates.json` (BLAST output,
   needed to compute `rago_support` at scoring time), and
   `scripts/llm_prompting_heldout.py` (frozen copy of `llm_prompting.py`
   restricted to the 5 rule-models and P1–P4, pointed at the 243-protein
   set).
2. Accession overlap — held-out vs. PROBE: 0. Held-out vs. ADAPT: 0.
   Held-out vs. BLAST pool accessions: 0. PROBE vs. ADAPT (sanity check
   on ADAPT's own exclusion logic): 0.
3. Duplicate accessions within the held-out 243: 0.
4. Missing FUNCTION text: 0 (guaranteed by eligibility rule). Missing raw
   sequence: 243/243 (expected — only `sequence_length` was captured
   during the draw; raw sequences must be fetched before BLAST retrieval,
   does not block P1–P4 calls).
5. GO/OBO file: hash verified identical to the frozen record
   (`923645000afcb1df`). Term-count bookkeeping discrepancy found
   (previously recorded 48,291; direct count of `[Term]` stanzas is
   48,321, including 10,058 obsolete terms) — **file is unchanged (hash
   match); this is a documentation correction only, not a data-integrity
   issue.** Held-out records with <3 experimental GO terms: 0 (would be
   a contradiction of the eligibility rule).
6. Model/prompt configuration: all 5 frozen model identifiers are present
   verbatim in PROBE's own `MODELS` list in `llm_prompting.py`. Prompt
   set confirmed as the expected 5 (`P1_zeroshot` ... `P5_selection`),
   with P5 correctly excluded from the frozen primary set.
7. Call-count arithmetic: N=243 confirmed; organism breakdown matches
   human=63/mouse=63/yeast=62/ecoli=55; total=14,580; per-protein=60;
   per-model=2,916; per-prompt=3,645 — all verified by direct computation,
   all match.

## 16. No-Retuning Commitment

No held-out result may be used to retune prompts, models, reliability
score weights, BLAST thresholds, score thresholds, or eligibility
criteria. A negative or weak held-out result is a valid scientific
finding and will **not** trigger post-hoc tuning, a redraw, or a change
to any frozen component in Sections 1–11.

## 17. Open-World Annotation Limitation

The held-out population has substantially sparser experimental GO
annotation than PROBE's dev set, particularly for biological_process
(BP presence 67.1% held-out vs. 93.8% PROBE, Cohen's d=-0.623; overall
total-GO-term Cohen's d=-0.645). Incomplete experimental ground truth can
cause biologically correct but currently uncurated predictions to be
counted as false negatives during scoring. This is reported as a
**potential evaluation limitation**, not a proven conservative bias on
the measured effect. BP-specific secondary results are particularly
susceptible to this limitation; CC-specific results are the least
affected (presence 88.5% held-out vs. 75.8% PROBE — not depressed at
all). This limitation was traced (via forensic analysis of PROBE's and
ADAPT's exact construction code) to population exhaustion — PROBE+ADAPT
already consumed essentially the entire population satisfying PROBE's
own eligibility rule at an earlier point in time — rather than to any
difference between the held-out qualification rule and PROBE's original
rule, which are nearly identical.
