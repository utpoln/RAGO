import json
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np

HERE = Path(__file__).parent
EXT_DIR = HERE.parent
RAGO = EXT_DIR.parent

heldout = json.load(open(RAGO / "scripts" / "heldout_sample_250.json"))
org_of = {r["accession"]: r["organism"] for r in heldout}
gt_lookup = {}
for r in heldout:
    for ns_full, ns_short in [("molecular_function","MF"),("biological_process","BP"),("cellular_component","CC")]:
        gt_lookup[(r["accession"], ns_full)] = set(t["go_id"] for t in r["go_terms"].get(ns_short, []))

openai_claims = json.load(open(EXT_DIR / "parsed" / "openai_claims.json"))
frozen_scores = json.load(open(HERE / "frozen_claim_score_lookup_READONLY.json"))

rows = []
for k in openai_claims:
    acc, ns, go_id = k.split("|")
    correct = int(go_id in gt_lookup.get((acc, ns), set()))
    score = frozen_scores.get(k, None)
    rows.append({"accession": acc, "namespace": ns, "go_id": go_id, "organism": org_of.get(acc,""),
                 "correct": correct, "frozen_score": score,
                 "in_frozen_set": score is not None})

print("="*90); print("A. OPENAI OVERALL PRECISION"); print("="*90)
total = len(rows)
correct_total = sum(r["correct"] for r in rows)
print(f"Total OpenAI claims (all, incl. not-in-frozen-set): {total}")
print(f"Correct: {correct_total}")
print(f"Precision: {correct_total/total:.4f}" if total else "n/a")
distinct_proteins = len(set(r["accession"] for r in rows))
print(f"Distinct proteins represented among these claims: {distinct_proteins}/243")

print("\nNamespace breakdown:")
for ns in ["molecular_function","biological_process","cellular_component"]:
    sub = [r for r in rows if r["namespace"]==ns]
    c = sum(r["correct"] for r in sub)
    print(f"  {ns:22s}: n={len(sub):3d}  correct={c:3d}  precision={c/len(sub):.4f}" if sub else f"  {ns}: n=0")

print("\nOrganism breakdown:")
for org in ["human","mouse","yeast","ecoli"]:
    sub = [r for r in rows if r["organism"]==org]
    c = sum(r["correct"] for r in sub)
    print(f"  {org:8s}: n={len(sub):3d}  correct={c:3d}  precision={c/len(sub):.4f}" if sub else f"  {org}: n=0")

print(); print("="*90); print("B. OVERLAP WITH FROZEN CLAIM SET"); print("="*90)
in_frozen = [r for r in rows if r["in_frozen_set"]]
not_in_frozen = [r for r in rows if not r["in_frozen_set"]]
print(f"Total OpenAI claims: {total}")
print(f"Overlapping frozen 5-model claim set: {len(in_frozen)} ({100*len(in_frozen)/total:.1f}%)")
print(f"NOT in frozen claim set (marked not_in_frozen_claim_set): {len(not_in_frozen)} ({100*len(not_in_frozen)/total:.1f}%)")
nf_correct = sum(r["correct"] for r in not_in_frozen)
print(f"  Of the not-in-frozen-set claims: {nf_correct}/{len(not_in_frozen)} correct "
      f"(precision={nf_correct/len(not_in_frozen):.4f})" if not_in_frozen else "")

print(); print("="*90); print("PRIMARY EXTERNAL-MODEL ANALYSIS: precision vs PRE-EXISTING frozen score"); print("="*90)
score_table = defaultdict(lambda: {"n":0,"c":0})
for r in in_frozen:
    score_table[r["frozen_score"]]["n"] += 1
    score_table[r["frozen_score"]]["c"] += r["correct"]
print(f"{'Frozen score':>14} {'OpenAI claims':>14} {'Correct':>8} {'Precision':>10}")
for s in range(2,15):
    d = score_table.get(s, {"n":0,"c":0})
    p = d["c"]/d["n"] if d["n"] else float('nan')
    print(f"{s:>14} {d['n']:>14} {d['c']:>8} {p:>10.4f}" if d["n"] else f"{s:>14} {0:>14} {0:>8} {'n/a':>10}")

print(f"\n{'Score >=':>10} {'OpenAI claims':>14} {'Correct':>8} {'Precision':>10}")
cum_n, cum_c = 0, 0
for s in range(14, 1, -1):
    d = score_table.get(s, {"n":0,"c":0})
    cum_n += d["n"]; cum_c += d["c"]
    p = cum_c/cum_n if cum_n else float('nan')
    print(f"{s:>10} {cum_n:>14} {cum_c:>8} {p:>10.4f}" if cum_n else f"{s:>10} {0:>14} {0:>8} {'n/a':>10}")

print(); print("="*90); print("C. AGREEMENT ENRICHMENT (binned)"); print("="*90)
bins = {"2-4": range(2,5), "5-8": range(5,9), "9-11": range(9,12), "12-14": range(12,15)}
for label, rng in bins.items():
    sub = [r for r in in_frozen if r["frozen_score"] in rng]
    if not sub:
        print(f"  {label}: n=0")
        continue
    c = sum(r["correct"] for r in sub)
    print(f"  score {label:6s}: n={len(sub):3d}  correct={c:3d}  precision={c/len(sub):.4f}")

print(); print("="*90); print("D. ORGANISM ROBUSTNESS (frozen score vs correctness, overlapping claims only)"); print("="*90)
for org in ["human","mouse","yeast","ecoli"]:
    sub = [r for r in in_frozen if r["organism"]==org]
    if not sub:
        print(f"  {org}: n=0 overlapping claims")
        continue
    c = sum(r["correct"] for r in sub)
    print(f"  {org:8s}: n={len(sub):3d}  correct={c:3d}  precision={c/len(sub):.4f}  "
        f"distinct_proteins={len(set(r['accession'] for r in sub))}")

print(); print("="*90); print("E. NAMESPACE ROBUSTNESS (frozen score vs correctness, overlapping claims only)"); print("="*90)
for ns in ["molecular_function","biological_process","cellular_component"]:
    sub = [r for r in in_frozen if r["namespace"]==ns]
    if not sub:
        print(f"  {ns}: n=0 overlapping claims")
        continue
    c = sum(r["correct"] for r in sub)
    flag = "  [BP sparse-ground-truth limitation applies -- see FROZEN_PROTOCOL.md Sec 17]" if ns=="biological_process" else ""
    print(f"  {ns:22s}: n={len(sub):3d}  correct={c:3d}  precision={c/len(sub):.4f}{flag}")

print(); print("="*90); print("F. PROTEIN-LEVEL ANALYSIS"); print("="*90)
proteins_represented = sorted(set(r["accession"] for r in rows))
print(f"Distinct proteins with >=1 OpenAI claim (any kind): {len(proteins_represented)}/243")
proteins_with_overlap_claim = sorted(set(r["accession"] for r in in_frozen))
print(f"Distinct proteins with >=1 claim overlapping the frozen set: {len(proteins_with_overlap_claim)}/243")
print("\nGiven only {} distinct proteins contribute any evaluable overlapping claim, a protein-level".format(len(proteins_with_overlap_claim)))
print("bootstrap (resampling from this tiny, non-random, budget-truncation-biased set of proteins)")
print("would produce an extremely wide and not-meaningfully-interpretable CI. Computing it anyway,")
print("clearly labeled, per the requirement to use protein-level resampling if a CI is reported:")

# protein-level bootstrap on the score>=9 "high score" bucket precision as an example,
# since that's the bucket most relevant to "does high frozen score predict correctness"
pn = defaultdict(lambda: [0,0])  # acc -> [n,c] for score>=9 claims
for r in in_frozen:
    if r["frozen_score"] >= 9:
        pn[r["accession"]][0] += 1
        pn[r["accession"]][1] += r["correct"]
accs = list(pn.keys())
if len(accs) >= 2:
    rng = np.random.default_rng(42)
    N = len(accs)
    vals = []
    for _ in range(2000):
        idx = rng.choice(N, size=N, replace=True)
        nn = sum(pn[accs[i]][0] for i in idx)
        cc = sum(pn[accs[i]][1] for i in idx)
        if nn > 0:
            vals.append(cc/nn)
    if vals:
        lo, hi = np.percentile(vals, [2.5, 97.5])
        point = sum(v[1] for v in pn.values())/sum(v[0] for v in pn.values())
        print(f"  score>=9 precision: point={point:.4f}  95% protein-bootstrap CI=[{lo:.4f},{hi:.4f}]  "
              f"(B=2000, seed=42, N_proteins={N})")
else:
    print(f"  Fewer than 2 distinct proteins contribute score>=9 overlapping claims (N={len(accs)}) -- "
          f"bootstrap not meaningful, not computed.")
