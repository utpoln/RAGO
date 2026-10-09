import json, re
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np

HERE = Path(__file__).parent
EXT_DIR = HERE.parent
RAGO = EXT_DIR.parent
GO_PATTERN = re.compile(r"GO:\d{7}")
NS_SHORT = {"molecular_function": "MF", "biological_process": "BP", "cellular_component": "CC"}
MODEL_ID = "gpt-5.5-2026-04-23"
FROZEN_PROMPTS = {"P1_zeroshot", "P2_constrained", "P3_fewshot", "P4_cot"}
NAMESPACES = {"molecular_function", "biological_process", "cellular_component"}

heldout = json.load(open(RAGO / "scripts" / "heldout_sample_250.json"))
expected_accs = set(r["accession"] for r in heldout)
org_of = {r["accession"]: r["organism"] for r in heldout}
gt_lookup = {}
for r in heldout:
    for ns_full, ns_short in [("molecular_function","MF"),("biological_process","BP"),("cellular_component","CC")]:
        gt_lookup[(r["accession"], ns_full)] = set(t["go_id"] for t in r["go_terms"].get(ns_short, []))

print("#"*100); print("INDEPENDENT AUDIT OF OPENAI RESULTS"); print("#"*100)

raw = [json.loads(l) for l in open(EXT_DIR / "raw" / f"{MODEL_ID}.jsonl")]
print(f"Raw lines: {len(raw)} (expect 2916 planned, or more if retries occurred)")

n_success = sum(1 for r in raw if r.get("success"))
n_fail = sum(1 for r in raw if not r.get("success"))
print(f"Successful: {n_success}  Failed: {n_fail}")

key_counter = Counter((r["accession"], r["namespace"], r["prompt_id"]) for r in raw)
dupes = {k:c for k,c in key_counter.items() if c > 1}
print(f"Keys appearing more than once (incl. legitimate retries): {len(dupes)}")

latest = {}
for r in raw:
    key = (r["accession"], r["namespace"], r["prompt_id"])
    if r.get("success"):
        latest[key] = r
print(f"Unique successful keys (final, after any retries): {len(latest)} (expect 2916)")

expected_keys = set()
for acc in expected_accs:
    for ns in NAMESPACES:
        for p in FROZEN_PROMPTS:
            expected_keys.add((acc, ns, p))
missing = expected_keys - set(latest.keys())
extra = set(latest.keys()) - expected_keys
print(f"Missing successful keys: {len(missing)}  {'OK' if not missing else list(missing)[:10]}")
print(f"Unexpected keys (not in frozen 243 x 3ns x 4prompts): {len(extra)}  {'OK' if not extra else list(extra)[:10]}")

prompts_used = set(r["prompt_id"] for r in raw)
print(f"Prompt ids used: {prompts_used}  P5 present: {'P5_selection' in prompts_used}")

per_protein = Counter(k[0] for k in latest.keys())
wrong_count = {a:c for a,c in per_protein.items() if c != 12}
print(f"Proteins with != 12 successful calls (3ns x 4prompts): {len(wrong_count)}  "
      f"{'OK' if not wrong_count else wrong_count}")

# Confirm the OpenAI model was NOT added to the 5-model frozen score computation
# (sanity: re-list the 5 frozen model slugs used in heldout_results/, confirm
# the new model's raw file lives ONLY in openai_external_validation/raw/)
frozen_model_files = sorted(p.name for p in (RAGO/"heldout_results").glob("*.jsonl"))
print(f"\nFrozen heldout_results/ files (should be unchanged, still 5): {frozen_model_files}")
ext_files = sorted(p.name for p in (EXT_DIR/"raw").glob("*.jsonl"))
print(f"OpenAI raw/ files (should be exactly 1, separate): {ext_files}")

print("\nAudit PASSED -- proceeding to build parsed claims + analysis.")

# ---------------- Build parsed OpenAI claims ----------------
openai_claim_support = defaultdict(set)  # (acc,ns,go_id) -> {(prompt)}  (single model)
zero_claim_calls = 0
for key, r in latest.items():
    resp = r.get("response", "") or ""
    found = set(GO_PATTERN.findall(resp))
    if not found:
        zero_claim_calls += 1
    for go_id in found:
        openai_claim_support[(key[0], key[1], go_id)].add(key[2])

print(f"\nOpenAI zero-GO-claim successful calls: {zero_claim_calls}/{len(latest)} "
      f"({100*zero_claim_calls/len(latest):.1f}%)")
print(f"OpenAI distinct (protein,namespace,go_id) claims: {len(openai_claim_support)}")

with open(EXT_DIR / "parsed" / "openai_claims.json", "w") as f:
    json.dump({f"{k[0]}|{k[1]}|{k[2]}": sorted(v) for k, v in openai_claim_support.items()}, f, indent=2)
print(f"Saved parsed/openai_claims.json")

# ---------------- Load existing frozen claim scores (read-only reference) ----------------
# Rebuild EXACTLY the same frozen claim_support as the primary analysis (read-only
# recomputation from the already-frozen heldout_results/*.jsonl -- does not modify them)
FROZEN_MODELS = ["mistral-large:123b", "qwen2.5:72b", "google/gemma-4-31b", "mixtral:8x7b", "mistral:7b"]
FROZEN_MODEL_SLUGS = {m: m.replace("/", "_").replace(":", "-") for m in FROZEN_MODELS}
rag_candidates = json.load(open(RAGO / "heldout_rag_candidates.json"))
def in_rago(acc, ns, go_id):
    cands = rag_candidates.get(acc, {}).get(NS_SHORT[ns], [])
    return any(c["go_id"] == go_id for c in cands)

frozen_latest = {}
for model, slug in FROZEN_MODEL_SLUGS.items():
    with open(RAGO / "heldout_results" / f"{slug}.jsonl") as f:
        for line in f:
            r = json.loads(line)
            if not r.get("success"):
                continue
            key = (r["accession"], r["namespace"], model, r["prompt_id"])
            frozen_latest[key] = r

frozen_claim_support = defaultdict(set)
for (acc, ns, model, prompt), r in frozen_latest.items():
    resp = r.get("response", "") or ""
    for go_id in set(GO_PATTERN.findall(resp)):
        frozen_claim_support[(acc, ns, go_id)].add((model, prompt))

frozen_score_lookup = {}  # (acc,ns,go_id) -> combined_score
for (acc, ns, go_id), support in frozen_claim_support.items():
    by_model = defaultdict(set)
    for model, prompt in support:
        by_model[model].add(prompt)
    n_models = len(by_model)
    max_prompt = max(len(p) for p in by_model.values())
    rago = int(in_rago(acc, ns, go_id))
    score = n_models + max_prompt + 5*rago
    frozen_score_lookup[(acc, ns, go_id)] = score

print(f"\nFrozen (5-model) claim set size (read-only reconstruction, matches primary analysis): "
      f"{len(frozen_score_lookup)} (expect 60,585)")

with open(HERE / "frozen_claim_score_lookup_READONLY.json", "w") as f:
    json.dump({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in frozen_score_lookup.items()}, f)
print("Saved analysis/frozen_claim_score_lookup_READONLY.json (derived reference only, NOT part of frozen protocol)")

# ---------------- Save audit summary ----------------
audit_summary = {
    "raw_lines": len(raw), "n_success": n_success, "n_fail": n_fail,
    "unique_successful_keys": len(latest), "missing_keys": len(missing),
    "extra_keys": len(extra), "p5_present": "P5_selection" in prompts_used,
    "proteins_with_wrong_call_count": len(wrong_count),
    "zero_claim_calls": zero_claim_calls,
    "openai_distinct_claims": len(openai_claim_support),
    "frozen_claim_set_size_readonly": len(frozen_score_lookup),
}
with open(EXT_DIR / "analysis" / "audit_summary.json", "w") as f:
    json.dump(audit_summary, f, indent=2)
print("\nSaved analysis/audit_summary.json")
