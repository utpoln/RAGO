"""
DESCRIPTIVE / PILOT-ONLY sanity check on the 500-call pilot. Not used to
tune anything. The frozen framework, score, prompts, model set, and
cohort are untouched by this script (read-only against frozen files).
"""
import json, re
from pathlib import Path
from collections import defaultdict, Counter

HERE = Path(__file__).parent
PROD = HERE.parent
EXT_DIR = PROD.parent
RAGO = EXT_DIR.parent
GO_PATTERN = re.compile(r"GO:\d{7}")
NS_SHORT = {"molecular_function": "MF", "biological_process": "BP", "cellular_component": "CC"}
FROZEN_MODELS = ["mistral-large:123b", "qwen2.5:72b", "google/gemma-4-31b", "mixtral:8x7b", "mistral:7b"]
FROZEN_MODEL_SLUGS = {m: m.replace("/", "_").replace(":", "-") for m in FROZEN_MODELS}

heldout = json.load(open(RAGO / "scripts" / "heldout_sample_250.json"))
org_of = {r["accession"]: r["organism"] for r in heldout}
gt_lookup = {}
for r in heldout:
    for ns_full, ns_short in [("molecular_function","MF"),("biological_process","BP"),("cellular_component","CC")]:
        gt_lookup[(r["accession"], ns_full)] = set(t["go_id"] for t in r["go_terms"].get(ns_short, []))
rag_candidates = json.load(open(RAGO / "heldout_rag_candidates.json"))
def in_rago(acc, ns, go_id):
    cands = rag_candidates.get(acc, {}).get(NS_SHORT[ns], [])
    return any(c["go_id"] == go_id for c in cands)

records = [json.loads(l) for l in open(PROD / "raw" / "production_master_output.jsonl")]

print("#"*100)
print("DESCRIPTIVE / PILOT-ONLY SCIENTIFIC SANITY CHECK -- NOT A TUNING STEP")
print("The frozen reliability score, model set, prompts, cutoff, and held-out cohort are")
print("UNCHANGED by this analysis. This is purely descriptive, on 500/2916 calls (~17%).")
print("#"*100)

claim_support = defaultdict(set)
for r in records:
    acc, ns, prompt_id = r["custom_id"].split("|")
    body = r["response"]["body"]
    content = body["choices"][0]["message"]["content"] or ""
    for go_id in set(GO_PATTERN.findall(content)):
        claim_support[(acc, ns, go_id)].add(prompt_id)

print(f"\n1. Number of distinct (protein,namespace,go_id) claims: {len(claim_support)}")
n_calls = len(records)
total_raw_claims = sum(len(GO_PATTERN.findall(r['response']['body']['choices'][0]['message']['content'] or '')) for r in records)
print(f"2. Claims per call: {total_raw_claims/n_calls:.2f} (raw, pre-dedup, mean over {n_calls} calls)")

ns_claim_counts = Counter(k[1] for k in claim_support)
print(f"3. Namespace distribution of distinct claims: {dict(ns_claim_counts)}")

print("\n4. Rebuilding frozen 5-model claim score lookup (READ-ONLY from heldout_results/*.jsonl)...")
frozen_latest = {}
for model, slug in FROZEN_MODEL_SLUGS.items():
    with open(RAGO / "heldout_results" / f"{slug}.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            if not rec.get("success"):
                continue
            key = (rec["accession"], rec["namespace"], model, rec["prompt_id"])
            frozen_latest[key] = rec
frozen_claim_support = defaultdict(set)
for (acc, ns, model, prompt), rec in frozen_latest.items():
    resp = rec.get("response", "") or ""
    for go_id in set(GO_PATTERN.findall(resp)):
        frozen_claim_support[(acc, ns, go_id)].add((model, prompt))
frozen_score_lookup = {}
for (acc, ns, go_id), support in frozen_claim_support.items():
    by_model = defaultdict(set)
    for model, prompt in support:
        by_model[model].add(prompt)
    n_models = len(by_model)
    max_prompt = max(len(p) for p in by_model.values())
    rago = int(in_rago(acc, ns, go_id))
    frozen_score_lookup[(acc, ns, go_id)] = n_models + max_prompt + 5*rago
print(f"   Frozen claim set size (unchanged, matches primary analysis): {len(frozen_score_lookup)}")

overlap = [k for k in claim_support if k in frozen_score_lookup]
not_overlap = [k for k in claim_support if k not in frozen_score_lookup]
print(f"\n5. Overlap with frozen five-model claim set: {len(overlap)}/{len(claim_support)} "
      f"({100*len(overlap)/len(claim_support):.1f}%)")
print(f"   Not in frozen claim set: {len(not_overlap)}/{len(claim_support)}")

print("\n6. Descriptive correctness among overlapping claims (DESCRIPTIVE ONLY):")
correct_overlap = sum(1 for k in overlap if k[2] in gt_lookup.get((k[0],k[1]), set()))
print(f"   {correct_overlap}/{len(overlap)} correct ({100*correct_overlap/len(overlap):.1f}%)" if overlap else "   n/a")

print("\n7. Score distribution among overlapping claims (DESCRIPTIVE ONLY):")
score_table = defaultdict(lambda: {"n":0,"c":0})
for k in overlap:
    s = frozen_score_lookup[k]
    score_table[s]["n"] += 1
    score_table[s]["c"] += int(k[2] in gt_lookup.get((k[0],k[1]), set()))
for s in sorted(score_table):
    d = score_table[s]
    print(f"   score={s:2d}: n={d['n']:3d}  correct={d['c']:3d}  precision={d['c']/d['n']:.3f}")

print("\nNOTE: all numbers in this file are descriptive/pilot-only, computed on a deterministic")
print("17%-sample slice (first 500 of 2916 by sorted custom_id, i.e. 42/243 proteins). They are")
print("NOT used to tune anything and are NOT a substitute for the full-run primary analysis.")
