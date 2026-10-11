# Reproducibility

This document distinguishes two different things a researcher might want
to do with this repository, because they have very different
requirements.

## A. Reproducing the analysis (recommended — no LLM inference required)

Every number reported in the manuscript can be reproduced directly from
the **raw LLM responses already included in this repository**, without
calling any model or inference service.

- `heldout_results/*.jsonl` — raw responses from the five frozen models
  on the 243-protein held-out cohort.
- `openai_external_validation/` — raw GPT-5.5 responses and analysis.
- `external_validation/<model>/*.jsonl` — raw responses from the four
  additional external-validation models (Llama 3.3 70B, Qwen3 32B,
  Gemma3 12B, GPT-oss-120B).
- `external_validation/analyze_external_model.py` — the analysis script
  used to produce every external-validation number in the manuscript
  (integrity audit, claim extraction, correctness, overlap with the
  frozen claim set, score-threshold precision, protein-level bootstrap).
- `external_validation/qwen3_truncation_sensitivity.py` — the Qwen3
  truncation sensitivity analysis reported in the manuscript's
  Limitations section.
- `openai_external_validation/analysis/frozen_claim_score_lookup_READONLY.json`
  — the read-only frozen five-model claim→score table that every
  external-validation score is looked up against. This file is never
  recomputed from any external model's output.

Running these scripts against the released raw responses reproduces the
reported tables and statistics exactly. **This path requires no API
key, no inference backend, and no re-execution of any LLM call.**

## B. Regenerating LLM responses (optional, not required to reproduce the analysis)

A researcher who wants to *regenerate* raw responses — rather than
reanalyze the ones already released — needs an inference backend
capable of serving the specified models, plus the exact prompts and
generation configuration documented in the manuscript's Methods
section and in `FROZEN_PROTOCOL.md` / `frozen_experiment_config.json`.

- **MindRouter** (University of Idaho's inference gateway,
  `https://mindrouter.uidaho.edu/v1`) was the backend used for every
  published experiment: the five frozen models, and four of the five
  external-validation models (Llama 3.3 70B, Qwen3 32B, Gemma3 12B,
  GPT-oss-120B). GPT-5.5 was called directly via the OpenAI API.
- MindRouter is an **execution/inference backend, not part of the
  scientific definition of the reliability score**. The score, the
  prompts, the held-out cohort, and every other scientific artifact
  are backend-independent and documented in full below.
- Another backend capable of serving a compatible implementation of a
  given model **may** be used instead, for models where that is
  technically possible — see `ollama.md` for one such option. Responses
  regenerated from a different backend, software version, quantization,
  or decoding implementation are **not guaranteed to be byte-identical**
  to the responses released in this repository, even for the same
  nominal model name. If exact reproduction of this study's numbers is
  the goal, use the released raw responses (Section A above) rather
  than regenerating them.

## C. Frozen artifacts (what defines the experiment, independent of any backend)

| Artifact | File |
|---|---|
| Frozen protocol (narrative) | `FROZEN_PROTOCOL.md` |
| Frozen protocol (machine-readable config + file hashes) | `frozen_experiment_config.json` |
| P1–P4 prompt definitions | `scripts/llm_prompting_heldout.py` (`build_prompts()`) |
| Held-out accession list (243 proteins) | `heldout_benchmark_243.json`, `scripts/heldout_sample_250.json` |
| GO ontology release + content hash | recorded in `frozen_experiment_config.json` |
| BLAST/RAGO retrieval configuration | `frozen_experiment_config.json`; code in `scripts/run_blast_retrieval.py` |
| Frozen reliability score definition | Methods §Frozen Reliability Framework in the manuscript; `scripts/llm_prompting_heldout.py` for the model/prompt set it is computed from |
| Frozen claim→score lookup (read-only) | `openai_external_validation/analysis/frozen_claim_score_lookup_READONLY.json` |
| Analysis code | `scripts/`, `openai_external_validation/analysis/`, `external_validation/*.py` |

None of the four open-source external-validation models, nor GPT-5.5,
were ever added to `n_models`, `max_prompt_consistency`,
`rago_support`, or the frozen score itself. Every external-model score
reported in the manuscript is a read-only lookup against the table
above, computed once from the five frozen models' own responses and
never modified.
