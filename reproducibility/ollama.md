# Optional: local inference with Ollama

**This is an optional example, not a requirement.** The analysis in
this repository is fully reproducible from the already-released raw
LLM responses (see `reproducibility/README.md`, Section A) without
running any inference at all. This document is only for a researcher
who specifically wants to regenerate responses locally for a model
Ollama can serve, as one example of a compatible local backend.

**Ollama is not required**, and this document does not claim that
using it will reproduce byte-identical responses to the ones released
in this repository. MindRouter was the actual backend used for every
published result; this is described in `reproducibility/README.md`.

## Which models this applies to

Of the models used in this study, MindRouter served some through an
Ollama-style backend and others through vLLM. This document only
applies, even potentially, to the former:

- Likely Ollama-compatible (served via an Ollama-style identifier on
  MindRouter in this study): `llama3.3:70b`, `mistral:7b`,
  `qwen2.5:72b`, `gemma3:12b`, and (for the frozen set) `mixtral:8x7b`
  and `mistral-large:123b`.
- **Not** confirmed Ollama-compatible (served via vLLM on MindRouter in
  this study, not through Ollama): `google/gemma-4-31b` (one of the
  five frozen models), `Qwen/Qwen3-32B`, and `openai/gpt-oss-120b`.
  Do not assume Ollama can serve these; check Ollama's own model
  library directly before attempting to.

Whether a specific model/version is actually published in Ollama's
public library changes over time and is not something this repository
tracks — verify directly at Ollama's own model library before relying
on this.

## High-level steps

1. **Install Ollama.** See Ollama's own installation instructions for
   your platform.
2. **Obtain a compatible implementation of the specified model**,
   where one is available in Ollama's public library (see the caveat
   above — not all models used in this study have one).
3. **Start the local inference service** (`ollama serve`, or the
   equivalent for your installation).
4. **Configure the RAGO runner to use the local endpoint.** The
   scripts in this repository (e.g.
   `external_validation/run_external_model.py`,
   `scripts/llm_prompting_heldout.py`) already support an
   OpenAI-compatible base URL; point `BASE_URL` at your local Ollama
   endpoint (typically `http://localhost:11434/v1`) instead of
   MindRouter's URL.
5. **Run P1–P4 on the released held-out accession set**
   (`heldout_benchmark_243.json` / `scripts/heldout_sample_250.json`)
   using the unmodified prompt-construction code
   (`build_prompts()` in `scripts/llm_prompting_heldout.py`), so that
   prompt content is identical to what was used for the published
   results.
6. **Run the provided analysis scripts** against your newly generated
   responses, exactly as described in `reproducibility/README.md`.

## What this will and will not tell you

Running inference locally through Ollama, even for a model listed
above as likely compatible, will not necessarily reproduce this
study's exact numbers: model weights, quantization, serving software,
and decoding implementation can all differ between Ollama's
distribution of a model and the version MindRouter served, even under
the same nominal model name. Treat any locally regenerated responses
as a new, independent run — comparable in design, not guaranteed to be
numerically identical — not as a reproduction of the released raw
response files.
