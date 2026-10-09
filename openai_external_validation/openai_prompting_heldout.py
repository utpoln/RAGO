"""
openai_prompting_heldout.py

SEPARATE external-model stress-test of the already-frozen 5-model
reliability framework. Does NOT modify, retune, or add to the frozen
primary experiment (RAGO/FROZEN_PROTOCOL.md, frozen_experiment_config.json,
heldout_results/). The OpenAI model's predictions are never added to
n_models; they are scored for correctness only, and separately looked up
against the PRE-EXISTING frozen combined_score where a claim overlaps.

Prompts (P1-P4 only) are IMPORTED from the frozen
scripts/llm_prompting_heldout.py::build_prompts() -- not retyped -- to
guarantee byte-identical wording and few-shot examples. P5 does not exist
in that module, so it cannot be invoked here either.

Model: gpt-5.5-2026-04-23 (dated, non-aliased snapshot; selected by the
user after being presented with alternatives).

Generation parameters (empirically determined before this run, not
invented -- see config.json):
  - max_completion_tokens=512 (this model rejects 'max_tokens')
  - temperature: NOT SETTABLE on this model (only default=1 allowed) --
    left unset, disclosed as a deviation from the frozen temperature=0.0
  - top_p: left unset (API default)
  - seed=42 (confirmed empirically to produce reproducible output)
  - no system message (matches frozen convention)

Usage:
    OPENAI_API_KEY=... python openai_prompting_heldout.py
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
import importlib.util

from openai import OpenAI

HERE = Path(__file__).parent
RAGO = HERE.parent

# Import build_prompts() directly from the frozen script -- no retyping.
spec = importlib.util.spec_from_file_location(
    "frozen_heldout_module", RAGO / "scripts" / "llm_prompting_heldout.py"
)
frozen_mod = importlib.util.module_from_spec(spec)
sys.argv = ["llm_prompting_heldout.py", "--api_key", "unused-not-called"]  # avoid CLI side effects on import
spec.loader.exec_module(frozen_mod)
build_prompts = frozen_mod.build_prompts
FROZEN_PROMPT_IDS = frozen_mod.FROZEN_PROMPT_IDS
NAMESPACES = frozen_mod.NAMESPACES

MODEL_ID = "gpt-5.5-2026-04-23"
BENCHMARK = RAGO / "heldout_benchmark_243.json"
EXPECTED_N = 243
RAW_DIR = HERE / "raw"
PARSED_DIR = HERE / "parsed"
LOGS_DIR = HERE / "logs"
OUT_FILE = RAW_DIR / f"{MODEL_ID}.jsonl"
MAX_COMPLETION_TOKENS = 512
SEED = 42
SLEEP_SEC = 0.4


def extract_response_content(choice) -> str:
    """Same convention as the frozen script: handle a possibly-empty
    content field, no reasoning_content fallback needed for this model
    (standard chat-completions, not exposed as a separate reasoning field
    here), but kept defensive."""
    content = choice.message.content
    if content is None:
        content = getattr(choice.message, "reasoning_content", None) or ""
    return content or ""


def call_model(client: OpenAI, prompt: str) -> dict:
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            seed=SEED,
        )
        content = extract_response_content(response.choices[0])
        return {
            "success": True,
            "response": content,
            "response_id": getattr(response, "id", ""),
            "model_returned": getattr(response, "model", ""),
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            } if response.usage else {},
        }
    except Exception as e:
        return {"success": False, "response": "", "error": str(e), "response_id": ""}


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


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    assert api_key, "OPENAI_API_KEY not found in environment -- refusing to run."

    with open(BENCHMARK) as f:
        entries = json.load(f)
    assert len(entries) == EXPECTED_N, f"Expected {EXPECTED_N} proteins, got {len(entries)} -- refusing to run."
    accs = [e["accession"] for e in entries]
    assert len(accs) == len(set(accs)), "Duplicate accessions -- refusing to run."

    RAW_DIR.mkdir(exist_ok=True)
    PARSED_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    completed = load_completed(OUT_FILE)
    total_planned = len(entries) * len(NAMESPACES) * len(FROZEN_PROMPT_IDS)
    print(f"Model: {MODEL_ID}")
    print(f"Proteins: {len(entries)}  Namespaces: {len(NAMESPACES)}  Prompts: {len(FROZEN_PROMPT_IDS)}")
    print(f"Total planned calls: {total_planned}")
    print(f"Already completed: {len(completed)}")

    client = OpenAI(api_key=api_key)
    start_time = datetime.now(timezone.utc).isoformat()
    n_done = 0
    with open(OUT_FILE, "a") as out_f:
        for entry in entries:
            accession = entry["accession"]
            for namespace in NAMESPACES:
                prompts = build_prompts(entry, namespace)
                assert set(prompts.keys()) == FROZEN_PROMPT_IDS
                for prompt_id, prompt_text in prompts.items():
                    key = (accession, namespace, prompt_id)
                    if key in completed:
                        continue
                    result = call_model(client, prompt_text)
                    record = {
                        "accession": accession,
                        "gene_name": entry.get("gene_name", ""),
                        "organism": entry.get("organism", ""),
                        "namespace": namespace,
                        "prompt_id": prompt_id,
                        "prompt_text": prompt_text,
                        "model": MODEL_ID,
                        "response": result["response"],
                        "response_id": result.get("response_id", ""),
                        "model_returned": result.get("model_returned", ""),
                        "system_fingerprint": result.get("system_fingerprint"),
                        "success": result["success"],
                        "error": result.get("error", ""),
                        "usage": result.get("usage", {}),
                        "ground_truth": entry.get(f"go_{namespace}", ""),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    out_f.write(json.dumps(record) + "\n")
                    out_f.flush()
                    n_done += 1
                    if n_done % 50 == 0:
                        print(f"  ...{n_done} calls this session (total incl. resumed: "
                              f"{len(completed)+n_done}/{total_planned})", flush=True)
                    time.sleep(SLEEP_SEC)
    end_time = datetime.now(timezone.utc).isoformat()
    print(f"\nDone. Calls made this session: {n_done}. Start: {start_time}  End: {end_time}")


if __name__ == "__main__":
    main()
