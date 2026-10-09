"""
llm_prompting_heldout.py

Frozen, restricted copy/adaptation of PROBE's llm_prompting.py for the
pre-registered 243-protein held-out confirmatory experiment (see
FROZEN_PROTOCOL.md). Differences from the original, each required by the
frozen protocol -- nothing else is changed:

  1. DATASET points to the frozen held-out set (heldout_benchmark_243.json,
     243 proteins), not PROBE's 1,000-protein dev set.
  2. MODELS is restricted to exactly the 5 frozen rule-models (ranks
     {1,3,5,7,9} of PROBE's published leaderboard). The other 5 PROBE
     models are not present in this file at all.
  3. P5_selection is DELETED from build_prompts() (not filtered -- the
     code path does not exist in this file), together with the
     _get_candidate_terms() helper it alone depended on. P5 cannot be
     executed accidentally because there is no code that builds it.
  4. OUTPUT_DIR is heldout_results/ (separate from PROBE's probe_results/
     and RAGO's rag_results/).
  5. Hard, loud startup assertions: exactly 243 proteins, exactly the 5
     frozen model identifiers, exactly 4 prompts per build -- the script
     raises and refuses to run rather than silently proceeding on any
     mismatch.
  6. Each logged record adds `response_id` (the OpenAI-compatible
     response object's own id, when available) as a request/response
     identifier, alongside everything PROBE already logs.

Per-call error handling (log success=false + error string, retry on
next run) is UNCHANGED from PROBE's original llm_prompting.py -- this
is the already-frozen, already-approved behavior (FROZEN_PROTOCOL.md
Sec. 12), not a silent skip: every attempted call is always written to
the output file.

Usage:
  python llm_prompting_heldout.py --api_key YOUR_KEY --model mistral-large:123b
  python llm_prompting_heldout.py --api_key YOUR_KEY --all_models
"""

import json
import re
import time
import argparse
from pathlib import Path
from datetime import datetime

from openai import OpenAI
from tqdm import tqdm

# ─────────────────────────────────────────────
# CONFIG (identical to PROBE's llm_prompting.py except where noted)
# ─────────────────────────────────────────────

BASE_URL_MINDROUTER = "https://mindrouter.uidaho.edu/v1"
BASE_URL_OLLAMA     = "http://localhost:11434/v1"
BASE_URL_CUSTOM     = "https://api.openai.com/v1"
BASE_URL    = BASE_URL_MINDROUTER

# CHANGED: frozen 243-protein held-out set, not PROBE's 1,000-protein dev set
DATASET     = "../heldout_benchmark_243.json"
EXPECTED_N  = 243

# CHANGED: separate output directory for the held-out run
OUTPUT_DIR  = Path("../heldout_results")

SLEEP_SEC   = 0.4
TEMPERATURE = 0.0
MAX_TOKENS  = 512

THINKING_MODELS = {
    "Qwen/Qwen3-32B",
    "qwen3:32b",
}

# CHANGED: restricted to exactly the 5 frozen rule-models
# (ranks {1,3,5,7,9} of PROBE's published Table 5 leaderboard --
# Mistral Large 123B, Qwen2.5 72B, Gemma-4 31B, Mixtral 8x7B, Mistral 7B).
# This is the complete model list for this script -- there is no 10-model
# option here.
MODELS = [
    "mistral-large:123b",
    "qwen2.5:72b",
    "google/gemma-4-31b",
    "mixtral:8x7b",
    "mistral:7b",
]
FROZEN_MODEL_SET = frozenset(MODELS)

NAMESPACES = ["molecular_function", "biological_process", "cellular_component"]
NAMESPACE_LABELS = {
    "molecular_function": "Molecular Function",
    "biological_process": "Biological Process",
    "cellular_component": "Cellular Component",
}

# CHANGED: P5 excluded by construction -- this is the complete prompt set.
FROZEN_PROMPT_IDS = frozenset({"P1_zeroshot", "P2_constrained", "P3_fewshot", "P4_cot"})

# ─────────────────────────────────────────────
# PROMPT BUILDERS  (identical wording to PROBE's P1-P4; P5 removed)
# ─────────────────────────────────────────────

def build_prompts(entry: dict, namespace: str, thinking_model: bool = False) -> dict:
    """Build P1-P4 ONLY. P5 (candidate-selection) does not exist in this
    file -- there is no function, no candidate list, no code path that
    could accidentally produce or send it."""
    gene          = entry.get("gene_name", "Unknown")
    protein       = entry.get("protein_name", "")
    org           = entry.get("organism_full", "")
    func          = entry.get("function_text", "")
    ns_label      = NAMESPACE_LABELS[namespace]
    protein_short = protein.split("{")[0].strip()

    context = f"Protein: {gene}\nFull name: {protein_short}\nOrganism: {org}"
    if func:
        context += f"\nKnown function: {func}"

    prefix = ""  # unchanged from PROBE: max_tokens=4096-style /no_think prefix not used

    prompts = {}

    prompts["P1_zeroshot"] = (
        f"{prefix}"
        f"You are an expert molecular biologist.\n\n"
        f"{context}\n\n"
        f"List the Gene Ontology (GO) {ns_label} terms that best describe "
        f"this protein. Provide GO IDs and term names. "
        f"Format each as: GO:XXXXXXX | term name"
    )

    prompts["P2_constrained"] = (
        f"{prefix}"
        f"You are an expert molecular biologist specializing in protein annotation.\n\n"
        f"{context}\n\n"
        f"Task: Predict ONLY the Gene Ontology {ns_label} "
        f"(GO {namespace.upper()[:2]}) terms for this protein.\n"
        f"Rules:\n"
        f"- List only experimentally supported functions\n"
        f"- Format each term as: GO:XXXXXXX | term name\n"
        f"- Do not include Biological Process or Cellular Component terms\n"
        f"- Output only the GO terms, nothing else"
    )

    few_shot_examples = _get_fewshot_examples(namespace)
    prompts["P3_fewshot"] = (
        f"{prefix}"
        f"You are an expert molecular biologist. "
        f"Predict Gene Ontology {ns_label} terms for proteins.\n\n"
        f"Here are three examples:\n\n"
        f"{few_shot_examples}\n\n"
        f"Now predict for:\n"
        f"{context}\n\n"
        f"List GO {ns_label} terms. Format: GO:XXXXXXX | term name"
    )

    prompts["P4_cot"] = (
        f"{prefix}"
        f"You are an expert molecular biologist.\n\n"
        f"{context}\n\n"
        f"Think step by step about what {ns_label} GO terms apply to this protein:\n"
        f"Step 1: What is the protein's primary biochemical activity?\n"
        f"Step 2: What molecular processes does it participate in?\n"
        f"Step 3: Based on your reasoning, list the GO {ns_label} terms.\n\n"
        f"Format final answer as: GO:XXXXXXX | term name"
    )

    assert set(prompts.keys()) == FROZEN_PROMPT_IDS, (
        f"build_prompts() produced {set(prompts.keys())}, expected exactly "
        f"{FROZEN_PROMPT_IDS} -- refusing to proceed."
    )
    return prompts


def _get_fewshot_examples(namespace: str) -> str:
    """Verbatim copy of PROBE's llm_prompting.py::_get_fewshot_examples() --
    byte-for-byte identical, not reworded."""
    examples = {
        "molecular_function": (
            "Example 1:\nProtein: TP53, Organism: Homo sapiens\n"
            "GO Molecular Function terms:\n"
            "GO:0003700 | DNA-binding transcription factor activity\n"
            "GO:0046872 | metal ion binding\n"
            "GO:0042802 | identical protein binding\n\n"
            "Example 2:\nProtein: EGFR, Organism: Homo sapiens\n"
            "GO Molecular Function terms:\n"
            "GO:0004714 | transmembrane receptor protein tyrosine kinase activity\n"
            "GO:0005515 | protein binding\n"
            "GO:0016301 | kinase activity\n\n"
            "Example 3:\nProtein: ACT1, Organism: Saccharomyces cerevisiae\n"
            "GO Molecular Function terms:\n"
            "GO:0005524 | ATP binding\n"
            "GO:0003779 | actin binding\n"
            "GO:0005198 | structural molecule activity"
        ),
        "biological_process": (
            "Example 1:\nProtein: TP53, Organism: Homo sapiens\n"
            "GO Biological Process terms:\n"
            "GO:0006915 | apoptotic process\n"
            "GO:0006351 | DNA-templated transcription\n"
            "GO:0007050 | cell cycle arrest\n\n"
            "Example 2:\nProtein: BRCA1, Organism: Homo sapiens\n"
            "GO Biological Process terms:\n"
            "GO:0006281 | DNA repair\n"
            "GO:0007050 | cell cycle arrest\n"
            "GO:0045786 | negative regulation of cell cycle\n\n"
            "Example 3:\nProtein: CDC28, Organism: Saccharomyces cerevisiae\n"
            "GO Biological Process terms:\n"
            "GO:0007049 | cell cycle\n"
            "GO:0006468 | protein phosphorylation\n"
            "GO:0045736 | negative regulation of cyclin-dependent protein kinase activity"
        ),
        "cellular_component": (
            "Example 1:\nProtein: TP53, Organism: Homo sapiens\n"
            "GO Cellular Component terms:\n"
            "GO:0005654 | nucleoplasm\n"
            "GO:0005829 | cytosol\n"
            "GO:0000785 | chromatin\n\n"
            "Example 2:\nProtein: MYH9, Organism: Homo sapiens\n"
            "GO Cellular Component terms:\n"
            "GO:0005925 | focal adhesion\n"
            "GO:0015629 | actin cytoskeleton\n"
            "GO:0032587 | ruffle membrane\n\n"
            "Example 3:\nProtein: TUB1, Organism: Saccharomyces cerevisiae\n"
            "GO Cellular Component terms:\n"
            "GO:0005737 | cytoplasm\n"
            "GO:0005874 | microtubule\n"
            "GO:0000779 | condensed chromosome, centromeric region"
        ),
    }
    return examples.get(namespace, "")


# ─────────────────────────────────────────────
# RESPONSE PARSER (identical to PROBE's)
# ─────────────────────────────────────────────

def extract_response_content(choice, model: str) -> str:
    content = choice.message.content
    if content is None:
        content = getattr(choice.message, "reasoning_content", None) or ""
    if content and "<think>" in content:
        after_think = re.split(r"</think>", content, flags=re.IGNORECASE)
        if len(after_think) > 1:
            content = after_think[-1].strip()
        else:
            content = content
    return content or ""


# ─────────────────────────────────────────────
# API CALLER (identical error-handling convention to PROBE's;
# CHANGED: also captures response_id as a request/response identifier)
# ─────────────────────────────────────────────

def call_model(client: OpenAI, model: str, prompt: str,
               is_thinking: bool = False) -> dict:
    max_tokens = MAX_TOKENS
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
        )
        content = extract_response_content(response.choices[0], model)
        return {
            "success":     True,
            "response":    content,
            "model":       model,
            "response_id": getattr(response, "id", ""),
            "usage": {
                "prompt_tokens":     response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            } if response.usage else {},
        }
    except Exception as e:
        return {
            "success":     False,
            "response":    "",
            "error":       str(e),
            "model":       model,
            "response_id": "",
        }


# ─────────────────────────────────────────────
# RESUME LOGIC (identical to PROBE's)
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
                    completed.add((rec["accession"], rec["namespace"], rec["prompt_id"]))
            except Exception:
                continue
    return completed


# ─────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────

def run(api_key: str, models: list, limit: int = None):
    # Loud startup assertions -- refuse to run on any configuration mismatch.
    assert set(models) <= FROZEN_MODEL_SET, (
        f"Requested models {set(models) - FROZEN_MODEL_SET} are not in the "
        f"frozen 5-model set {FROZEN_MODEL_SET} -- refusing to run."
    )

    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"Loading dataset from {DATASET} ...")
    with open(DATASET) as f:
        entries = json.load(f)

    if limit:
        entries = entries[:limit]
        print(f"Running in LIMIT mode: {limit} proteins only (NOT the frozen full run)")
    else:
        assert len(entries) == EXPECTED_N, (
            f"Held-out dataset has {len(entries)} proteins, expected exactly "
            f"{EXPECTED_N} -- refusing to run. The frozen accession list must "
            f"not be modified."
        )
        accs = [e["accession"] for e in entries]
        assert len(accs) == len(set(accs)), "Duplicate accessions in held-out dataset -- refusing to run."

    print(f"Total proteins     : {len(entries):,}")
    print(f"Models to run      : {len(models)}  {models}")
    print(f"Prompts per protein: 4 (P1-P4; P5 does not exist in this script)")
    print(f"Namespaces         : {len(NAMESPACES)}")
    print(f"Total API calls    : {len(entries)*4*len(NAMESPACES)*len(models):,}\n")

    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    for model in models:
        is_thinking = model in THINKING_MODELS
        model_slug  = model.replace("/", "_").replace(":", "-")
        output_file = OUTPUT_DIR / f"{model_slug}.jsonl"
        completed   = load_completed(output_file)

        print(f"\n{'='*60}")
        print(f"Model: {model}")
        print(f"Output: {output_file}")
        print(f"Thinking mode: {'YES (reasoning_content fallback active)' if is_thinking else 'NO'}  |  max_tokens={MAX_TOKENS}")
        print(f"Already completed: {len(completed):,} calls")
        print(f"{'='*60}")

        with open(output_file, "a") as out_f:
            for entry in tqdm(entries, desc=model_slug):
                accession = entry["accession"]
                for namespace in NAMESPACES:
                    prompts = build_prompts(entry, namespace, thinking_model=is_thinking)
                    for prompt_id, prompt_text in prompts.items():
                        key = (accession, namespace, prompt_id)
                        if key in completed:
                            continue

                        result = call_model(client, model, prompt_text, is_thinking=is_thinking)

                        record = {
                            "accession":    accession,
                            "gene_name":    entry.get("gene_name", ""),
                            "organism":     entry.get("organism", ""),
                            "namespace":    namespace,
                            "prompt_id":    prompt_id,
                            "prompt_text":  prompt_text,
                            "model":        model,
                            "response":     result["response"],
                            "response_id":  result.get("response_id", ""),
                            "success":      result["success"],
                            "error":        result.get("error", ""),
                            "usage":        result.get("usage", {}),
                            "ground_truth": entry.get(f"go_{namespace}", ""),
                            "timestamp":    datetime.utcnow().isoformat(),
                        }

                        out_f.write(json.dumps(record) + "\n")
                        out_f.flush()
                        time.sleep(SLEEP_SEC)

    print("\nPrompting complete!")
    print(f"   Results saved in: {OUTPUT_DIR}/")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key",    required=True,
                        help="API key. Use 'ollama' for local Ollama inference.")
    parser.add_argument("--model",      default=None,
                        help="One of the 5 frozen models exactly; see MODELS.")
    parser.add_argument("--all_models", action="store_true",
                        help="Run all 5 frozen models (there is no 10-model option in this script).")
    parser.add_argument("--limit",      type=int, default=None)
    parser.add_argument("--base_url",   default=None)
    args = parser.parse_args()

    if args.base_url:
        BASE_URL = args.base_url

    if args.all_models:
        selected = MODELS
    elif args.model:
        if args.model not in FROZEN_MODEL_SET:
            raise SystemExit(
                f"'{args.model}' is not one of the 5 frozen models {sorted(FROZEN_MODEL_SET)} "
                f"-- refusing to run."
            )
        selected = [args.model]
    else:
        print("Please specify --model MODEL_NAME or --all_models")
        exit(1)

    run(api_key=args.api_key, models=selected, limit=args.limit)
