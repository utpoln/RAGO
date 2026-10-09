# OpenAI External-Model Validation

A **separate** stress test of the already-frozen 5-model reliability
framework (`../FROZEN_PROTOCOL.md`), using one OpenAI model never involved
in building that framework. Does not modify, overwrite, or append to any
frozen primary file — verified by before/after SHA-256 hashes.

See `OPENAI_EXTERNAL_PROTOCOL.md` for the full protocol, including a
critical methodological finding (reasoning-token budget exhaustion caused
98% of calls to return empty output).

- `config.json` — generation parameters, model selection, call plan
- `raw/` — one JSONL file (`gpt-5.5-2026-04-23.jsonl`), full API records, append-only
- `parsed/openai_claims.json` — deduplicated GO claims parsed from successful responses
- `analysis/` — audit scripts, read-only frozen-score lookup, final analysis
- `logs/run.log` — run progress log
- `run_manifest.json` — full reproducibility manifest
- `OPENAI_EXTERNAL_VALIDATION_REPORT.md` — results, clearly separated into frozen-primary / new-external / exploratory / limitations
