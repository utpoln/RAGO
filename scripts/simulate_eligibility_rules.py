"""
Item 5: simulate candidate eligibility under rules A/B/C/D on the current
fresh (untouched) eligible pool, WITHOUT any LLM calls -- UniProt fetches
only, reusing the exact same pre-registered seed=42 shuffle order already
used in the real draw (loaded from heldout_draw_audit_log.json for full
auditability/reproducibility).

Rules:
  A: >=3 total experimental GO terms, any namespace (current held-out rule,
     minus the FUNCTION-text requirement is reported separately)
  B: >=1 experimental term in at least 2 of {MF,BP,CC}
  C: >=1 experimental term in all 3 of {MF,BP,CC}
  D: PROBE's exact original rule: >=3 total experimental GO terms, any
     namespace, NO function-text requirement (verified from
     dataset_preparation.py)

For yeast and ecoli the full eligible pool is fetched (pool size ~2,500,
proven feasible). For human and mouse, a large deterministic prefix of the
pre-registered shuffle order is fetched (sample, not exhaustive -- flagged
as such) because full enumeration (~9-10k each) would take too long.
"""
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/Users/kallolnaha/Documents/mix_projects/mindrouter/RAGO/scripts")
from draw_heldout_sample import fetch_entry, count_experimental_go, has_function_text

SEED = 42
BATCH_SIZE = 20
MAX_WORKERS = 8
HUMAN_MOUSE_SAMPLE = 800   # deterministic prefix of shuffle order (not exhaustive)

with open("/Users/kallolnaha/Documents/mix_projects/mindrouter/RAGO/scripts/heldout_draw_audit_log.json") as f:
    audit = json.load(f)
eligible_pools = audit["eligible_pools"]

rng = random.Random(SEED)
ORGANISM_ORDER = ["human", "mouse", "yeast", "ecoli"]

results = {}
for org in ORGANISM_ORDER:
    pool = sorted(eligible_pools[org])
    shuffled = pool[:]
    rng.shuffle(shuffled)

    if org in ("human", "mouse"):
        to_fetch = shuffled[:HUMAN_MOUSE_SAMPLE]
        exhaustive = False
    else:
        to_fetch = shuffled
        exhaustive = True

    print(f"=== {org}: fetching {len(to_fetch)}/{len(pool)} "
          f"({'exhaustive' if exhaustive else 'sample, deterministic shuffle prefix'}) ===", flush=True)

    records = []
    pos = 0
    t0 = time.time()
    while pos < len(to_fetch):
        batch = to_fetch[pos: pos + BATCH_SIZE]
        pos += BATCH_SIZE
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            entries = list(ex.map(fetch_entry, batch))
        for acc, entry in zip(batch, entries):
            if entry is None:
                continue
            go_counts = count_experimental_go(entry)
            func_ok = has_function_text(entry)
            records.append({"accession": acc, "mf": go_counts["MF"], "bp": go_counts["BP"],
                             "cc": go_counts["CC"], "total": sum(go_counts.values()),
                             "has_function_text": func_ok})
        if pos % 200 == 0 or pos >= len(to_fetch):
            print(f"  ...{min(pos, len(to_fetch))}/{len(to_fetch)} fetched "
                  f"({time.time()-t0:.0f}s elapsed)", flush=True)

    results[org] = {"pool_size": len(pool), "sampled_n": len(to_fetch), "exhaustive": exhaustive,
                     "records": records}
    print(f"  Done: {len(records)} valid entries fetched for {org}\n", flush=True)

with open("/Users/kallolnaha/Documents/mix_projects/mindrouter/RAGO/scripts/eligibility_simulation_raw.json", "w") as f:
    json.dump(results, f)
print("Saved eligibility_simulation_raw.json")
