"""
RAGO: LLM Prompting Pipeline (Retrieval-Augmented GO Annotation)

Same ten models, same MindRouter/Ollama calling convention, same output
schema as PROBE's llm_prompting.py, so RAGO results can be evaluated
with the same pipeline and compared directly to PROBE's P1-P5 leaderboard.

The only difference from P5 (PROBE's candidate-selection format): the
candidate list is retrieved per-protein via BLAST homology against the
non-benchmark pool (run_blast_retrieval.py), not a single fixed global
top-15 list.

Usage:
  python llm_prompting_rag.py --api_key YOUR_KEY --model mistral-large:123b --limit 50
  python llm_prompting_rag.py --api_key YOUR_KEY --all_models
"""

import json
import time
import argparse
from pathlib import Path
from datetime import datetime

from openai import OpenAI
from tqdm import tqdm

# ─────────────────────────────────────────────
# CONFIG (identical to PROBE for direct comparability)
# ─────────────────────────────────────────────

BASE_URL_MINDROUTER = "https://mindrouter.uidaho.edu/v1"
BASE_URL_OLLAMA      = "http://localhost:11434/v1"
BASE_URL             = BASE_URL_MINDROUTER

BENCHMARK       = "benchmark_master.json"
RAG_CANDIDATES  = "rag_candidates.json"
OUTPUT_DIR      = Path("rag_results")
SLEEP_SEC       = 0.4
TEMPERATURE     = 0.0
MAX_TOKENS      = 512

THINKING_MODELS = {"Qwen/Qwen3-32B", "qwen3:32b"}

MODELS = [
    "llama3.3:70b", "llama3.1:8b",
    "mistral-large:123b", "mistral:7b",
    "qwen2.5:72b", "qwen2.5:7b",
    "Qwen/Qwen3-32B",
    "gemma3:12b", "google/gemma-4-31b",
    "mixtral:8x7b",
]

NAMESPACES = ["molecular_function", "biological_process", "cellular_component"]
NAMESPACE_LABELS = {
    "molecular_function": "Molecular Function",
    "biological_process": "Biological Process",
    "cellular_component": "Cellular Component",
}
NS_SHORT = {"molecular_function": "MF", "biological_process": "BP", "cellular_component": "CC"}


# ─────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────

def build_rag_prompt(entry: dict, namespace: str, candidates: list) -> str:
    """P5-style candidate-selection prompt, but candidates are the
    per-protein BLAST-retrieved set rather than a fixed global list."""
    gene     = entry.get("gene_name", "Unknown")
    protein  = entry.get("protein_name", "").split("{")[0].strip()
    org      = entry.get("organism_full", "")
    func     = entry.get("function_text", "")
    ns_label = NAMESPACE_LABELS[namespace]

    context = f"Protein: {gene}\nFull name: {protein}\nOrganism: {org}"
    if func:
        context += f"\nKnown function: {func}"

    cand_lines = "\n".join(f"{c['go_id']} | {c['term_name']}" for c in candidates)

    return (
        f"You are an expert molecular biologist.\n\n"
        f"{context}\n\n"
        f"From the following GO {ns_label} terms, retrieved from proteins "
        f"homologous to this one, select ALL that apply.\n"
        f"Candidate terms:\n{cand_lines}\n\n"
        f"List only the matching terms as: GO:XXXXXXX | term name\n"
        f"If none apply, write: NONE"
    )


# ─────────────────────────────────────────────
# RESPONSE PARSER (same as PROBE, handles reasoning models)
# ─────────────────────────────────────────────

def extract_response_content(choice) -> str:
    content = choice.message.content
    if content is None:
        content = getattr(choice.message, "reasoning_content", None) or ""
    if content and "<think>" in content:
        import re
        after_think = re.split(r"</think>", content, flags=re.IGNORECASE)
        if len(after_think) > 1:
            content = after_think[-1].strip()
    return content or ""


def call_model(client: OpenAI, model: str, prompt: str) -> dict:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        content = extract_response_content(response.choices[0])
        return {
            "success": True,
            "response": content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            } if response.usage else {},
        }
    except Exception as e:
        return {"success": False, "response": "", "error": str(e)}


# ─────────────────────────────────────────────
# RESUME LOGIC
# ─────────────────────────────────────────────

def load_completed(output_file: Path) -> set:
    completed = set()
    if not output_file.exists():
        return completed
    with open(output_file) as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("success", False):
                    completed.add((rec["accession"], rec["namespace"]))
            except Exception:
                continue
    return completed


# ─────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────

def run(api_key: str, models: list, limit: int = None):
    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"Loading benchmark from {BENCHMARK} ...")
    with open(BENCHMARK) as f:
        entries = json.load(f)
    print(f"Loading RAG candidates from {RAG_CANDIDATES} ...")
    with open(RAG_CANDIDATES) as f:
        rag_candidates = json.load(f)

    if limit:
        entries = entries[:limit]
        print(f"Running in LIMIT mode: {limit} proteins only")

    total_calls = 0
    no_candidate_count = 0

    print(f"Total proteins : {len(entries):,}")
    print(f"Models to run  : {len(models)}")
    print(f"Namespaces     : {len(NAMESPACES)}  (1 RAG prompt per protein x namespace)\n")

    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    for model in models:
        model_slug = model.replace("/", "_").replace(":", "-")
        output_file = OUTPUT_DIR / f"{model_slug}.jsonl"
        completed = load_completed(output_file)

        print(f"\n{'='*60}\nModel: {model}\nOutput: {output_file}\n"
              f"Already completed: {len(completed):,} calls\n{'='*60}")

        with open(output_file, "a") as out_f:
            for entry in tqdm(entries, desc=model_slug):
                accession = entry["accession"]
                for namespace in NAMESPACES:
                    key = (accession, namespace)
                    if key in completed:
                        continue

                    ns_short = NS_SHORT[namespace]
                    candidates = rag_candidates.get(accession, {}).get(ns_short, [])

                    if not candidates:
                        # No BLAST hit above threshold for this protein/namespace.
                        # Record this explicitly rather than silently falling
                        # back -- it changes what "RAG prediction" means here.
                        record = {
                            "accession": accession,
                            "gene_name": entry.get("gene_name", ""),
                            "organism": entry.get("organism", ""),
                            "namespace": namespace,
                            "prompt_id": "RAG_selection",
                            "model": model,
                            "response": "NONE",
                            "success": True,
                            "error": "",
                            "usage": {},
                            "n_candidates": 0,
                            "no_retrieval": True,
                            "ground_truth": entry.get(f"go_{namespace}", ""),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        out_f.write(json.dumps(record) + "\n")
                        out_f.flush()
                        no_candidate_count += 1
                        continue

                    prompt_text = build_rag_prompt(entry, namespace, candidates)
                    result = call_model(client, model, prompt_text)
                    total_calls += 1

                    record = {
                        "accession": accession,
                        "gene_name": entry.get("gene_name", ""),
                        "organism": entry.get("organism", ""),
                        "namespace": namespace,
                        "prompt_id": "RAG_selection",
                        "prompt_text": prompt_text,
                        "model": model,
                        "response": result["response"],
                        "success": result["success"],
                        "error": result.get("error", ""),
                        "usage": result.get("usage", {}),
                        "n_candidates": len(candidates),
                        "no_retrieval": False,
                        "ground_truth": entry.get(f"go_{namespace}", ""),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    out_f.write(json.dumps(record) + "\n")
                    out_f.flush()
                    time.sleep(SLEEP_SEC)

    print(f"\nAPI calls made this run: {total_calls:,}")
    print(f"No-retrieval records (skipped LLM call): {no_candidate_count:,}")
    print("\n✅ RAG prompting complete!")
    print(f"   Results saved in: {OUTPUT_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--all_models", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--base_url", default=None)
    args = parser.parse_args()

    if args.base_url:
        BASE_URL = args.base_url

    if args.all_models:
        selected = MODELS
    elif args.model:
        selected = [args.model]
    else:
        print("Please specify --model MODEL_NAME or --all_models")
        exit(1)

    run(api_key=args.api_key, models=selected, limit=args.limit)
