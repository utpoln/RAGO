"""
run_external_model.py

Generic runner for the previously-unseen-external-model validation
experiment. This file is NEW -- it does not modify, and is not
imported by, any frozen file. It READS two things from the frozen
five-model script, by import (never retyped, to guarantee
byte-identical prompt text and response-parsing logic):

  - build_prompts()           (scripts/llm_prompting_heldout.py)
  - extract_response_content() (scripts/llm_prompting_heldout.py)

It also reads the frozen held-out protein list
(heldout_benchmark_243.json) read-only. It writes ONLY inside its own
per-model subdirectory under external_validation/ -- it never writes
to heldout_results/, never writes to openai_external_validation/,
and never writes to any frozen top-level file.

These four models (Llama 3.3 70B, Qwen3 32B, Gemma3 12B, Cohere
Command-A 111B) are external-validation models only. Nothing in this
script computes, updates, or references n_models, max_prompt_consistency,
rago_support, or the combined score -- this script only generates and
logs raw predictions. Scoring against the frozen five-model claim set
happens later, in a separate read-only analysis step, exactly as was
already done for GPT-5.5.

Usage (pilot example -- Command-A technical pilot, 16 proteins x 3
namespaces x 1 prompt = 48 calls):
  MINDROUTER_API_KEY=... python run_external_model.py \
      --model command-a:111b --label command_a_111b \
      --n-proteins 16 --namespaces molecular_function,biological_process,cellular_component \
      --prompts P1_zeroshot --max-tokens 512 --pilot

Usage (full run -- 243 proteins x 3 namespaces x 4 prompts = 2,916 calls):
  MINDROUTER_API_KEY=... python run_external_model.py \
      --model command-a:111b --label command_a_111b \
      --max-tokens 512
"""

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from datetime import datetime, timezone

from openai import OpenAI
from tqdm import tqdm

RAGO_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://mindrouter.uidaho.edu/v1"
HELDOUT_FILE = RAGO_ROOT / "heldout_benchmark_243.json"
EXPECTED_N = 243
ALL_NAMESPACES = ["molecular_function", "biological_process", "cellular_component"]
ALL_PROMPTS = ["P1_zeroshot", "P2_constrained", "P3_fewshot", "P4_cot"]
SLEEP_SEC = 0.4  # identical pacing convention to the frozen script

# Imported, not retyped, from the frozen five-model script.
spec = importlib.util.spec_from_file_location(
    "llm_prompting_heldout", RAGO_ROOT / "scripts" / "llm_prompting_heldout.py"
)
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)
build_prompts = frozen.build_prompts
extract_response_content = frozen.extract_response_content


def prompt_set_hash(entries, namespaces, prompt_ids) -> str:
    """Hash of the exact prompt text that will be sent, for the run
    manifest -- lets us later prove byte-identical prompt content to
    the frozen five-model / GPT-5.5 runs for shared (protein, namespace,
    prompt_id) combinations."""
    h = hashlib.sha256()
    for entry in entries[:5]:  # sample is enough to prove identity; full set is huge
        for ns in namespaces:
            prompts = build_prompts(entry, ns, thinking_model=False)
            for pid in prompt_ids:
                h.update(prompts[pid].encode())
    return h.hexdigest()[:16]


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


def call_model(client, model, prompt_text, max_tokens, temperature):
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = resp.choices[0]
        content = extract_response_content(choice, model)
        return {
            "success": True,
            "response": content,
            "finish_reason": getattr(choice, "finish_reason", None),
            "response_id": getattr(resp, "id", ""),
            "usage": {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            } if resp.usage else {},
            "elapsed_sec": round(time.time() - t0, 2),
        }
    except Exception as e:
        return {
            "success": False,
            "response": "",
            "error": str(e),
            "elapsed_sec": round(time.time() - t0, 2),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="MindRouter model identifier")
    ap.add_argument("--label", required=True, help="output subdirectory name under external_validation/")
    ap.add_argument("--api-key-env", default="MINDROUTER_API_KEY")
    ap.add_argument("--api-key-file", default="~/.mindrouter_key",
                     help="fallback: file containing the raw key, read if the env var is unset")
    ap.add_argument("--n-proteins", type=int, default=EXPECTED_N)
    ap.add_argument("--namespaces", default=",".join(ALL_NAMESPACES))
    ap.add_argument("--prompts", default=",".join(ALL_PROMPTS))
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--pilot", action="store_true", help="marks this run as a technical pilot, not scientific data")
    args = ap.parse_args()

    import os
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        key_path = Path(args.api_key_file).expanduser()
        if key_path.exists():
            api_key = key_path.read_text().strip()
    assert api_key, (
        f"No key found: {args.api_key_env} is unset and {args.api_key_file} "
        f"does not exist -- refusing to run."
    )

    namespaces = args.namespaces.split(",")
    prompt_ids = args.prompts.split(",")
    assert set(namespaces) <= set(ALL_NAMESPACES)
    assert set(prompt_ids) <= set(ALL_PROMPTS)

    with open(HELDOUT_FILE) as f:
        all_entries = json.load(f)
    assert len(all_entries) == EXPECTED_N, f"Held-out file has {len(all_entries)} proteins, expected {EXPECTED_N}"
    entries = all_entries[: args.n_proteins]

    out_dir = RAGO_ROOT / "external_validation" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    model_slug = args.model.replace("/", "_").replace(":", "-")
    suffix = "_pilot" if args.pilot else ""
    output_file = out_dir / f"{model_slug}{suffix}.jsonl"

    completed = load_completed(output_file)
    total_planned = len(entries) * len(namespaces) * len(prompt_ids)
    print(f"Model               : {args.model}")
    print(f"Label               : {args.label}  ({'PILOT' if args.pilot else 'FULL RUN'})")
    print(f"Proteins            : {len(entries)}")
    print(f"Namespaces          : {namespaces}")
    print(f"Prompts             : {prompt_ids}")
    print(f"max_tokens          : {args.max_tokens}   temperature: {args.temperature}")
    print(f"Thinking-model mode : {args.thinking}")
    print(f"Total planned calls : {total_planned:,}")
    print(f"Already completed   : {len(completed):,} (resume)")
    print(f"Output file         : {output_file}")

    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    combos = [
        (entry, ns, pid)
        for entry in entries
        for ns in namespaces
        for pid in prompt_ids
        if (entry["accession"], ns, pid) not in completed
    ]

    with open(output_file, "a") as f:
        for entry, ns, pid in tqdm(combos, desc=f"{args.label}:{model_slug}"):
            prompts = build_prompts(entry, ns, thinking_model=args.thinking)
            prompt_text = prompts[pid]
            result = call_model(client, args.model, prompt_text, args.max_tokens, args.temperature)
            record = {
                "accession": entry["accession"],
                "namespace": ns,
                "prompt_id": pid,
                "model": args.model,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **result,
            }
            f.write(json.dumps(record) + "\n")
            f.flush()
            time.sleep(SLEEP_SEC)

    # Manifest (written/overwritten after each invocation of this script)
    manifest = {
        "model": args.model,
        "label": args.label,
        "pilot": args.pilot,
        "base_url": BASE_URL,
        "n_proteins_this_invocation": len(entries),
        "namespaces": namespaces,
        "prompt_ids": prompt_ids,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "thinking_mode": args.thinking,
        "sleep_sec": SLEEP_SEC,
        "prompt_sample_hash": prompt_set_hash(entries, namespaces, prompt_ids),
        "output_file": str(output_file),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frozen_score_note": "This script never computes or modifies n_models, "
                              "max_prompt_consistency, rago_support, or the combined "
                              "score. External model output is scored only by a "
                              "separate, later, read-only analysis step against the "
                              "existing frozen five-model claim set.",
    }
    manifest_file = out_dir / f"run_manifest{suffix}.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest written to {manifest_file}")


if __name__ == "__main__":
    main()
