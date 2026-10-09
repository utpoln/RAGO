"""
run_500_pilot.py -- selects the first 500 requests (by sorted custom_id)
from the already-audited, unmodified 2,916-request set and submits ONLY
those via the already-audited submit_and_wait() function. Does not
modify submit_production_batch.py in any way -- reuses it as a library.

Selection rule (deterministic, documented, applied before any API call):
  1. build_all_requests() -- the exact, unmodified, audited 2,916-request list
  2. sort by custom_id ascending
  3. take the first 500

No scientific parameter is touched. Results are appended to the SAME
MASTER_OUTPUT file submit_production_batch.py's main() will later read,
so the remaining-2,416 submission (when authorized) will naturally skip
these 500 via the already-audited resume logic.
"""
import json
import os
from pathlib import Path
from openai import OpenAI
import submit_production_batch as prod

HERE = Path(__file__).parent
PILOT_N = 500

def main():
    all_requests = prod.build_all_requests()  # unmodified, audited function
    assert len(all_requests) == 2916

    sorted_requests = sorted(all_requests, key=lambda r: r["custom_id"])
    pilot_requests = sorted_requests[:PILOT_N]
    assert len(pilot_requests) == PILOT_N
    assert len(set(r["custom_id"] for r in pilot_requests)) == PILOT_N

    manifest = {
        "selection_rule": "build_all_requests() [unmodified] -> sort by custom_id ascending -> take first 500",
        "n_selected": PILOT_N,
        "selected_custom_ids": [r["custom_id"] for r in pilot_requests],
        "config": {
            "model": prod.MODEL_ID, "reasoning_effort": prod.REASONING_EFFORT,
            "max_completion_tokens": prod.MAX_COMPLETION_TOKENS, "seed": prod.SEED,
        },
    }
    with open(HERE / "logs" / "pilot500_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Pilot manifest saved BEFORE any API call: {HERE / 'logs' / 'pilot500_manifest.json'}")
    print(f"Selected {len(pilot_requests)} requests, first={pilot_requests[0]['custom_id']}, "
          f"last={pilot_requests[-1]['custom_id']}")

    api_key = os.environ.get("OPENAI_API_KEY")
    assert api_key, "OPENAI_API_KEY not set"
    client = OpenAI(api_key=api_key)

    records = prod.submit_and_wait(pilot_requests, "pilot500", client)  # unmodified, audited function
    with open(prod.MASTER_OUTPUT, "a") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    print(f"Appended {len(records)} records to {prod.MASTER_OUTPUT}")


if __name__ == "__main__":
    main()
