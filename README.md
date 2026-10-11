# External Validation of a Multi-Signal Reliability Framework for LLM-Based Gene Ontology Annotation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Status: manuscript in preparation](https://img.shields.io/badge/status-manuscript%20in%20preparation-orange.svg)](#)

> **Kallol Naha, Hasan Jamil**
> Department of Computer Science, University of Idaho
> naha7197@vandals.uidaho.edu | jamil@uidaho.edu

---

## Overview

This repository holds the code, frozen protocol, and raw results for a study of whether a **reliability score for LLM-generated Gene Ontology (GO) claims** — built and frozen using only existing development data — generalizes to genuinely unseen proteins, and whether that same frozen ranking transfers to an external model family that played no part in building it.

The reliability score combines three signals already observable at inference time: cross-model agreement (`n_models`), cross-prompt consistency (`max_prompt_consistency`), and homology-based retrieval support (`rago_support`, from BLAST against a frozen candidate pool). All three components, the five models and four prompts used to compute them, and the primary endpoint were fixed and timestamped **before** any prediction was generated on the held-out cohort (see `FROZEN_PROTOCOL.md` / `frozen_experiment_config.json`).

**Primary external validation** (five frozen models, 243 held-out proteins never seen during score construction): at the prespecified top-10%-coverage operating point, precision reached **4.78%** against a **0.70%** unselected baseline — a protein-level paired bootstrap difference of **+4.08 percentage points** (95% CI [+3.71, +4.47]).

**External model-family validation** (GPT-5.5, a model that contributed nothing to the score): among the 50.2% of GPT-5.5 claims that matched an existing scored claim, empirical correctness likewise rose with the same frozen score, from 5.41% at the lowest observed score to 42.48% at the highest.

> **Note:** The manuscript and LaTeX source will be released upon journal acceptance.

---

## Key Findings

| # | Result |
|---|---|
| 1 | Primary 10%-coverage precision: **4.78%** vs. **0.70%** baseline (+4.08 pp, 95% CI [+3.71, +4.47]) on 243 held-out proteins |
| 2 | Precision increases with the frozen score across its full range (0.09% at score 2 → 38.28% at score 14), not strictly monotonic at every individual value |
| 3 | Leave-one-model-out: removing any single one of the five frozen models never drops precision below 4.78%; cross-model agreement is the strongest individual component evaluated (not an orthogonal/causal decomposition) |
| 4 | GPT-5.5 (never used to build the score): cumulative precision 14.85%–42.48% across the same score thresholds, among the 2,410 overlapping claims |
| 5 | Held-out cohort is substantially sparser in experimental GO annotation than the development benchmark (mean 3.84 vs. 7.67 terms/protein, Cohen's *d* = −0.645) — reported as a property of the validation design |

---

## Repository Structure

```
RAGO/
├── FROZEN_PROTOCOL.md                  # Full frozen protocol (timestamped, pre-registered-in-spirit)
├── frozen_experiment_config.json       # Machine-readable frozen config + file hashes
│
├── benchmark_master.json               # PROBE's 1,000-protein development set (reused, not modified)
├── pool_proteins.fasta                 # ADAPT's 25,460-protein candidate pool (BLAST retrieval source)
├── pool_blastdb.*                      # Frozen BLAST database built from the pool above
├── pool_go_lookup.json                 # GO-term lookup for the candidate pool
│
├── heldout_benchmark_243.json          # The 243-protein held-out cohort (human 63, mouse 63, yeast 62, E. coli 55)
├── heldout_query_proteins.fasta        # Held-out protein sequences (for BLAST)
├── heldout_rag_candidates.json         # BLAST retrieval candidates for the held-out cohort
├── heldout_blast_hits.tsv              # Raw BLAST hits, held-out cohort
│
├── scripts/
│   ├── draw_heldout_sample.py          # Held-out cohort sampling (seed=42, full audit log)
│   ├── simulate_eligibility_rules.py   # Eligibility-rule simulation used before freezing the design
│   ├── fetch_heldout_sequences.py      # Pull sequences for sampled accessions
│   ├── extract_sequences.py            # Sequence extraction utilities
│   ├── build_pool_go_lookup.py         # Build the GO lookup for the candidate pool
│   ├── run_blast_retrieval.py          # BLASTp retrieval against the frozen pool DB
│   ├── check_retrieval_quality.py      # Retrieval sanity checks
│   ├── evaluate_rag.py                 # RAG/BLAST-support evaluation
│   ├── decompose_rag_unmatched.py      # Diagnostic decomposition of unmatched RAG candidates
│   ├── temporal_holdout_rag.py         # Temporal-holdout style checks
│   ├── llm_prompting_heldout.py        # Primary 5-model inference on the held-out cohort (P1–P4)
│   └── llm_prompting_rag.py            # RAG-augmented inference variant
│
├── heldout_results/                    # Raw primary-model responses (JSONL, one file per model)
│   ├── mistral-large-123b.jsonl
│   ├── qwen2.5-72b.jsonl
│   ├── google_gemma-4-31b.jsonl
│   ├── mixtral-8x7b.jsonl
│   ├── mistral-7b.jsonl
│   └── run_manifest.json               # Full reproducibility manifest
│
├── rag_results/                        # BLAST/RAG-support evaluation outputs (subset of models)
├── rag_evaluation/
│   └── rag_leaderboard.json
│
├── openai_external_validation/         # External model-family validation (GPT-5.5)
│   ├── README.md                       # Subfolder-specific documentation
│   ├── OPENAI_EXTERNAL_PROTOCOL.md     # Protocol for this stress test
│   ├── OPENAI_EXTERNAL_VALIDATION_REPORT.md
│   ├── openai_prompting_heldout.py     # GPT-5.5 inference on the identical 243-protein cohort
│   ├── config.json
│   ├── raw/gpt-5.5-2026-04-23.jsonl    # Raw GPT-5.5 API records
│   ├── parsed/openai_claims.json       # Deduplicated GPT-5.5 claims
│   ├── analysis/                       # Audit + final analysis scripts
│   ├── production/                     # Production batch submission scripts
│   └── pilot_cost_optimization/        # Pilot batch-cost study (preceding the full run)
│
├── external_validation/                # Four additional external-validation models
│   ├── run_external_model.py           # Generic runner (reuses the frozen P1-P4 prompt builder)
│   ├── analyze_external_model.py       # Generic integrity audit + analysis pipeline
│   ├── qwen3_truncation_sensitivity.py # Qwen3 truncation-sensitivity analysis
│   ├── combined_external_validation_summary.json
│   ├── llama3_3_70b/                   # Llama 3.3 70B raw responses + analysis
│   ├── qwen3_32b/                      # Qwen3 32B raw responses + analysis
│   ├── gemma3_12b/                     # Gemma3 12B raw responses + analysis
│   ├── gpt_oss_120b/                   # GPT-oss-120B raw responses + analysis
│   └── command_a_111b/                 # Discontinued (pilot only, see DISCONTINUED.md)
│
├── reproducibility/                    # How to reproduce the analysis vs. regenerate responses
│   ├── README.md
│   └── ollama.md                       # Optional local-inference guidance (not required)
│
└── manuscript/                         # Manuscript source -- not included in this repository;
                                         # released upon journal acceptance (see note above)
```

---

## Documentation

Every markdown document in this repository, linked from here:

- [`FROZEN_PROTOCOL.md`](FROZEN_PROTOCOL.md) — the full frozen protocol for the primary five-model experiment (score definition, held-out eligibility rule, tie-handling rule, bootstrap procedure, timestamps)
- **External model-family validation (GPT-5.5)**
  - [`openai_external_validation/README.md`](openai_external_validation/README.md) — subfolder overview
  - [`openai_external_validation/OPENAI_EXTERNAL_PROTOCOL.md`](openai_external_validation/OPENAI_EXTERNAL_PROTOCOL.md) — protocol for the GPT-5.5 stress test
  - [`openai_external_validation/OPENAI_EXTERNAL_VALIDATION_REPORT.md`](openai_external_validation/OPENAI_EXTERNAL_VALIDATION_REPORT.md) — results report
  - [`openai_external_validation/pilot_cost_optimization/PILOT_PROTOCOL.md`](openai_external_validation/pilot_cost_optimization/PILOT_PROTOCOL.md) — pilot batch-cost protocol
  - [`openai_external_validation/pilot_cost_optimization/pilot_report.md`](openai_external_validation/pilot_cost_optimization/pilot_report.md) — pilot results
- **Additional external-validation models**
  - [`external_validation/command_a_111b/DISCONTINUED.md`](external_validation/command_a_111b/DISCONTINUED.md) — why the Cohere Command-A 111B run was discontinued after a technical pilot (never used as scientific data)
- **Reproducibility**
  - [`reproducibility/README.md`](reproducibility/README.md) — reproducing the analysis from released data vs. regenerating LLM responses, plus the full frozen-artifact index
  - [`reproducibility/ollama.md`](reproducibility/ollama.md) — optional local-inference guidance (Ollama is not required; MindRouter is the backend actually used for every published result)

---

## The Frozen Reliability Score

```
combined_score = n_models + max_prompt_consistency + 5 x rago_support     (range: 2-14)
```

| Component | Definition | Range |
|---|---|---|
| `n_models` | Number of the five frozen models producing this exact GO identifier for this protein/namespace, pooled across P1–P4 | 1–5 |
| `max_prompt_consistency` | Maximum, over the five models, of the number of P1–P4 prompts under which that model produced this exact GO identifier | 1–4 |
| `rago_support` | 1 if the GO identifier appears among the top-15 BLAST-retrieved candidate terms for this protein/namespace, else 0 | 0–1 |

The score, the five models, the four prompts, the BLAST database/parameters, the GO release, the held-out eligibility rule, the tie-handling rule, and the bootstrap procedure were all fixed in `frozen_experiment_config.json` **before** any held-out prediction was generated, and are not retuned based on held-out or external-model results.

---

## Models Evaluated

### Primary (frozen score, five models, P1–P4)

Selected from PROBE's already-published ten-model leaderboard by a fixed, mechanical rule (ranks 1, 3, 5, 7, 9) applied before any held-out or external-model result was examined:

| Model | MindRouter identity |
|---|---|
| Mistral Large 123B | `mistral-large:123b` |
| Qwen2.5 72B | `qwen2.5:72b` |
| Gemma-4 31B | `google/gemma-4-31b` |
| Mixtral 8x7B | `mixtral:8x7b` |
| Mistral 7B | `mistral:7b` |

P5 (closed-set candidate selection) is excluded from the frozen score by design — it is structurally different from the open-ended generation task used by P1–P4, and none of the three score components depend on P5 data.

### External model family (not used to build the score)

| Model | Role |
|---|---|
| GPT-5.5 (`gpt-5.5-2026-04-23`) | External validation only; evaluated under the identical frozen score and endpoint on the same 243-protein cohort |

---

## Held-Out Cohort

243 proteins, disjoint from both PROBE's 1,000-protein development set and ADAPT's 25,460-protein candidate pool (verified zero overlap):

| Organism | N |
|---|---|
| *Homo sapiens* | 63 |
| *Mus musculus* | 63 |
| *Saccharomyces cerevisiae* | 62 |
| *Escherichia coli* | 55 |
| **Total** | **243** |

Eligibility rule (identical to the rule used to build the development pool, not changed after observing the held-out distribution shift): ≥3 total experimental-evidence GO terms (evidence codes IDA, IMP, IPI, IGI, IEP, EXP, HDA, HMP, HGI, HEP) and a non-empty UniProt FUNCTION comment. Sampling seed 42.

---

## Reproduce Results

### Step 1 — Draw the held-out cohort (pre-built sample included)
```bash
python scripts/draw_heldout_sample.py
python scripts/fetch_heldout_sequences.py
```

### Step 2 — BLAST retrieval (RAGO support signal)
```bash
python scripts/run_blast_retrieval.py
python scripts/check_retrieval_quality.py
```

### Step 3 — Primary five-model inference (P1–P4, held-out cohort)
```bash
python scripts/llm_prompting_heldout.py
```
Requires a MindRouter-compatible endpoint; see `scripts/llm_prompting_heldout.py` for configuration. 14,580 calls (243 proteins x 3 namespaces x 5 models x 4 prompts).

### Step 4 — RAG/BLAST-support evaluation
```bash
python scripts/evaluate_rag.py
```

### Step 5 — External model-family validation (GPT-5.5)
```bash
cd openai_external_validation
python openai_prompting_heldout.py
python analysis/audit_and_analyze.py
python analysis/final_analysis.py
```
Requires `OPENAI_API_KEY` as an environment variable — never pass API keys on the command line or hardcode them. See `openai_external_validation/README.md` and `OPENAI_EXTERNAL_PROTOCOL.md` for the full protocol, including a methodological finding on reasoning-token budget exhaustion during early pilot runs.

All raw results (`heldout_results/*.jsonl`, `openai_external_validation/raw/*.jsonl`) and the full frozen-protocol audit trail are included so the primary and external-validation results can be re-derived directly from source without re-running inference.

---

## License

MIT License, consistent with the companion PROBE repository.
Development data derived from UniProt Swiss-Prot ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).

---

## Contact

| | |
|---|---|
| **Kallol Naha** | naha7197@vandals.uidaho.edu |
| **Hasan Jamil** | jamil@uidaho.edu |
| **Institution** | Department of Computer Science, University of Idaho |
| **Issues** | Please open a GitHub issue |
