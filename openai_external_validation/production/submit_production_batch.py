"""
submit_production_batch.py -- PRODUCTION Batch submission for the full
243-protein x 3-namespace x 4-prompt OpenAI external-validation run.

STATUS AS OF WRITING: NOT YET EXECUTED. This file exists for code audit
only -- main() has not been called. No production API calls have been
made from this script.

Design, carried over from the approved pilot (Config A) with no changes:
  - model = gpt-5.5-2026-04-23
  - reasoning_effort = "low"
  - max_completion_tokens = 4000
  - seed = 42 (fixed, identical for every request)
  - Batch API (not synchronous)
  - Prompts imported unmodified from scripts/llm_prompting_heldout.py::build_prompts()

Writes ONLY to this directory (production/raw/, production/logs/,
production/analysis/) -- never to heldout_results/, FROZEN_PROTOCOL.md,
frozen_experiment_config.json, scripts/heldout_sample_250.json, or the
archived pilot/previous-failed-run directories.

Retry design: a request is considered "needs retry" if the API call
itself failed, OR finish_reason != "stop" (covers finish_reason="length",
i.e. an incomplete/truncated scientific response), exactly matching the
bar established and used in the pilot's independent audit. Retries never
resubmit a request that already has a successful (api_ok AND
finish_reason=="stop") result on file. All retry rounds use the IDENTICAL
request body (model/reasoning_effort/max_completion_tokens/seed) -- no
scientific parameter is ever changed between rounds. Retry rounds are
bounded (MAX_RETRY_ROUNDS), not an unbounded loop.
"""
import json
import re
import sys
import time
import importlib.util
from pathlib import Path
from openai import OpenAI

HERE = Path(__file__).parent
EXT_DIR = HERE.parent
RAGO = EXT_DIR.parent

# ---- Import build_prompts() unmodified from the frozen script ----
spec = importlib.util.spec_from_file_location("m", RAGO / "scripts" / "llm_prompting_heldout.py")
frozen_mod = importlib.util.module_from_spec(spec)
_real_argv = sys.argv
sys.argv = ["x", "--api_key", "unused"]
spec.loader.exec_module(frozen_mod)
sys.argv = _real_argv
build_prompts = frozen_mod.build_prompts
NAMESPACES = frozen_mod.NAMESPACES
FROZEN_PROMPT_IDS = frozen_mod.FROZEN_PROMPT_IDS

MODEL_ID = "gpt-5.5-2026-04-23"
REASONING_EFFORT = "low"
MAX_COMPLETION_TOKENS = 4000
SEED = 42
BENCHMARK = RAGO / "heldout_benchmark_243.json"
EXPECTED_N_PROTEINS = 243
EXPECTED_TOTAL_REQUESTS = 243 * 3 * 4  # = 2916
MAX_RETRY_ROUNDS = 3
MASTER_OUTPUT = HERE / "raw" / "production_master_output.jsonl"
GO_PATTERN = re.compile(r"GO:\d{7}")


def build_all_requests():
    """Builds the full, deterministic set of 2,916 requests. Pure local
    computation -- no API calls. custom_id = 'accession|namespace|prompt_id'."""
    with open(BENCHMARK) as f:
        entries = json.load(f)
    assert len(entries) == EXPECTED_N_PROTEINS, (
        f"Expected {EXPECTED_N_PROTEINS} proteins, got {len(entries)} -- refusing to build requests."
    )
    accs = [e["accession"] for e in entries]
    assert len(accs) == len(set(accs)), "Duplicate accessions in benchmark file -- refusing."

    requests = []
    seen_ids = set()
    for entry in entries:
        for ns in NAMESPACES:
            prompts = build_prompts(entry, ns)
            assert set(prompts.keys()) == FROZEN_PROMPT_IDS, (
                f"build_prompts returned unexpected prompt ids: {set(prompts.keys())}"
            )
            for prompt_id, prompt_text in prompts.items():
                custom_id = f"{entry['accession']}|{ns}|{prompt_id}"
                assert custom_id not in seen_ids, f"Duplicate custom_id generated: {custom_id}"
                seen_ids.add(custom_id)
                requests.append({
                    "custom_id": custom_id,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": MODEL_ID,
                        "messages": [{"role": "user", "content": prompt_text}],
                        "max_completion_tokens": MAX_COMPLETION_TOKENS,
                        "reasoning_effort": REASONING_EFFORT,
                        "seed": SEED,
                    },
                })
    assert len(requests) == EXPECTED_TOTAL_REQUESTS, (
        f"Built {len(requests)} requests, expected {EXPECTED_TOTAL_REQUESTS} -- refusing to proceed."
    )
    return requests


def load_existing_results():
    """Reads the master output file (if any) and returns:
      - a dict custom_id -> most-recent raw record
      - the set of custom_ids that are 'scientifically usable' (api_ok AND finish_reason=='stop')
    Never deletes or rewrites existing lines -- new rounds only APPEND."""
    by_id = {}
    if MASTER_OUTPUT.exists():
        with open(MASTER_OUTPUT) as f:
            for line in f:
                rec = json.loads(line)
                by_id[rec["custom_id"]] = rec  # later lines (later retry rounds) override earlier ones
    usable_ids = set()
    for cid, rec in by_id.items():
        api_ok = rec.get("error") is None and (rec.get("response") or {}).get("status_code") == 200
        finish_reason = None
        if api_ok:
            finish_reason = rec["response"]["body"]["choices"][0]["finish_reason"]
        if api_ok and finish_reason == "stop":
            usable_ids.add(cid)
    return by_id, usable_ids


def submit_and_wait(requests_subset, round_label, client, poll_interval_sec=20, max_polls=2000):
    """Submits ONE batch for the given requests, polls with a BOUNDED
    number of iterations (max_polls), returns the list of raw output
    records (and error records, if any) for this round only."""
    if not requests_subset:
        return []
    input_path = HERE / "raw" / f"production_input_{round_label}.jsonl"
    with open(input_path, "w") as f:
        for r in requests_subset:
            f.write(json.dumps(r) + "\n")

    upload = client.files.create(file=open(input_path, "rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=upload.id, endpoint="/v1/chat/completions", completion_window="24h",
        metadata={"round": round_label, "purpose": "production_external_validation"},
    )
    with open(HERE / "logs" / f"batch_id_{round_label}.txt", "w") as f:
        f.write(batch.id)
    print(f"[{round_label}] submitted batch {batch.id} with {len(requests_subset)} requests", flush=True)

    for i in range(max_polls):
        b = client.batches.retrieve(batch.id)
        print(f"[{round_label}] poll {i}: status={b.status} counts={b.request_counts}", flush=True)
        if b.status in ("completed", "failed", "expired", "cancelled"):
            break
        time.sleep(poll_interval_sec)
    else:
        raise RuntimeError(f"[{round_label}] exceeded max_polls={max_polls} without reaching a terminal state")

    records = []
    if b.output_file_id:
        content = client.files.content(b.output_file_id).text
        records.extend(json.loads(l) for l in content.strip().split("\n") if l)
    if b.error_file_id:
        content = client.files.content(b.error_file_id).text
        error_records = [json.loads(l) for l in content.strip().split("\n") if l]
        print(f"[{round_label}] {len(error_records)} records in the error file", flush=True)
        records.extend(error_records)
    return records


def needs_retry(rec):
    """A record needs retry iff the API call failed OR the response is
    scientifically incomplete (finish_reason != 'stop'). This is the ONLY
    retry trigger -- content quality (e.g. zero GO ids with finish_reason
    == 'stop') does NOT trigger a retry, matching the frozen convention
    that a genuine zero-claim prediction is valid, not a failure."""
    api_ok = rec.get("error") is None and (rec.get("response") or {}).get("status_code") == 200
    if not api_ok:
        return True
    finish_reason = rec["response"]["body"]["choices"][0]["finish_reason"]
    return finish_reason != "stop"


def main():
    import os
    api_key = os.environ.get("OPENAI_API_KEY")
    assert api_key, "OPENAI_API_KEY not set -- refusing to run."
    client = OpenAI(api_key=api_key)

    all_requests = build_all_requests()
    all_by_id = {r["custom_id"]: r for r in all_requests}

    for round_num in range(1, MAX_RETRY_ROUNDS + 1):
        existing_by_id, usable_ids = load_existing_results()
        remaining_ids = set(all_by_id.keys()) - usable_ids
        if not remaining_ids:
            print(f"All {len(all_by_id)} requests have a usable result. Done.")
            break
        remaining_requests = [all_by_id[cid] for cid in sorted(remaining_ids)]
        print(f"=== ROUND {round_num}: {len(remaining_requests)} requests remaining "
              f"(usable so far: {len(usable_ids)}) ===")
        new_records = submit_and_wait(remaining_requests, f"round{round_num}", client)
        with open(MASTER_OUTPUT, "a") as f:
            for rec in new_records:
                f.write(json.dumps(rec) + "\n")
    else:
        print(f"WARNING: exhausted {MAX_RETRY_ROUNDS} retry rounds; some requests may still be incomplete. "
              f"Not retrying further automatically -- report and stop.")


if __name__ == "__main__":
    main()
