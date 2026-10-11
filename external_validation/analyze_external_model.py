"""
analyze_external_model.py

Generic integrity-audit + scientific-analysis pipeline for one
external-validation model, extending EXACTLY the methodology already
used and frozen for GPT-5.5
(openai_external_validation/analysis/audit_and_analyze.py +
final_analysis.py) -- same GO-pattern regex, same ground-truth source,
same frozen-claim-score lookup (read-only, reused as-is, NOT
recomputed), same protein-level bootstrap procedure.

This script NEVER touches n_models, max_prompt_consistency,
rago_support, or the combined score. It reads the existing
analysis/frozen_claim_score_lookup_READONLY.json (already built once,
read-only, identical regardless of which external model is being
analyzed) and looks up each external claim's score, if it exists.
A claim with no entry in that lookup is NOT in the frozen five-model
claim set and is reported separately -- it is never assigned a score.

Usage:
  python analyze_external_model.py --label llama3_3_70b \
      --raw-file llama3_3_70b/llama3.3-70b.jsonl --model-id llama3.3:70b
"""

import argparse
import json
import re
from pathlib import Path
from collections import defaultdict, Counter

import numpy as np

HERE = Path(__file__).resolve().parent
RAGO = HERE.parent
GO_PATTERN = re.compile(r"GO:\d{7}")
NS_SHORT = {"molecular_function": "MF", "biological_process": "BP", "cellular_component": "CC"}
NAMESPACES = ["molecular_function", "biological_process", "cellular_component"]
FROZEN_PROMPTS = {"P1_zeroshot", "P2_constrained", "P3_fewshot", "P4_cot"}
FROZEN_SCORE_LOOKUP_PATH = RAGO / "openai_external_validation" / "analysis" / "frozen_claim_score_lookup_READONLY.json"

B_BOOTSTRAP = 2000
SEED = 42


def protein_bootstrap_precision(per_protein_nc, B=B_BOOTSTRAP, seed=SEED):
    """per_protein_nc: dict accession -> [n, c]. Protein-level resample,
    pooled precision per replicate. Returns (point, lo95, hi95, n_proteins)
    or None if fewer than 2 contributing proteins."""
    accs = list(per_protein_nc.keys())
    if len(accs) < 2:
        return None
    rng = np.random.default_rng(seed)
    N = len(accs)
    vals = []
    for _ in range(B):
        idx = rng.choice(N, size=N, replace=True)
        nn = sum(per_protein_nc[accs[i]][0] for i in idx)
        cc = sum(per_protein_nc[accs[i]][1] for i in idx)
        if nn > 0:
            vals.append(cc / nn)
    if not vals:
        return None
    lo, hi = np.percentile(vals, [2.5, 97.5])
    total_n = sum(v[0] for v in per_protein_nc.values())
    total_c = sum(v[1] for v in per_protein_nc.values())
    point = total_c / total_n if total_n else float("nan")
    return {"point": point, "ci_lo": float(lo), "ci_hi": float(hi), "n_proteins": N, "B": B, "seed": seed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--raw-file", required=True)
    ap.add_argument("--model-id", required=True)
    args = ap.parse_args()

    out_dir = HERE / args.label
    raw_path = Path(args.raw_file)
    if not raw_path.is_absolute():
        raw_path = HERE / raw_path

    report = {"label": args.label, "model_id": args.model_id}

    # ---------------- Ground truth + organism lookup (identical source to GPT-5.5 analysis) ----------------
    heldout = json.load(open(RAGO / "scripts" / "heldout_sample_250.json"))
    expected_accs = set(r["accession"] for r in heldout)
    org_of = {r["accession"]: r["organism"] for r in heldout}
    gt_lookup = {}
    for r in heldout:
        for ns_full, ns_short in [("molecular_function", "MF"), ("biological_process", "BP"), ("cellular_component", "CC")]:
            gt_lookup[(r["accession"], ns_full)] = set(t["go_id"] for t in r["go_terms"].get(ns_short, []))

    # ============================================================
    # STEP 1: INTEGRITY AUDIT
    # ============================================================
    raw = [json.loads(l) for l in open(raw_path)]
    n_raw = len(raw)
    n_success_raw = sum(1 for r in raw if r.get("success"))
    n_fail_raw = sum(1 for r in raw if not r.get("success"))

    key_counter = Counter((r["accession"], r["namespace"], r["prompt_id"]) for r in raw)
    dupes = {f"{k[0]}|{k[1]}|{k[2]}": c for k, c in key_counter.items() if c > 1}

    # "latest" = final retained record per key (success=True; this pipeline's
    # resume logic only re-attempts keys with NO prior success=True record --
    # see run_external_model.py:load_completed(). A truncated-but-successful
    # call (finish_reason="length") IS counted success=True and is therefore
    # NOT retried, identically to how the frozen 5-model script and the
    # GPT-5.5 script both treat truncation (not a retry-eligible failure;
    # only an API exception is retry-eligible).
    latest = {}
    for r in raw:
        key = (r["accession"], r["namespace"], r["prompt_id"])
        if r.get("success"):
            latest[key] = r

    expected_keys = set()
    for acc in expected_accs:
        for ns in NAMESPACES:
            for p in FROZEN_PROMPTS:
                expected_keys.add((acc, ns, p))
    missing = expected_keys - set(latest.keys())
    extra = set(latest.keys()) - expected_keys

    prompts_used = set(r["prompt_id"] for r in raw)
    per_protein_calls = Counter(k[0] for k in latest.keys())
    wrong_count = {a: c for a, c in per_protein_calls.items() if c != 12}

    # Truncation trace
    truncated_final = [r for key, r in latest.items() if r.get("finish_reason") == "length"]
    other_finish = Counter(r.get("finish_reason") for r in latest.values())
    # unparseable: a retained record whose response field is missing/not a string
    unparseable = [k for k, r in latest.items() if not isinstance(r.get("response"), str)]

    report["integrity"] = {
        "raw_lines": n_raw,
        "raw_successful": n_success_raw,
        "raw_failed": n_fail_raw,
        "duplicate_keys_in_raw_file": len(dupes),
        "duplicate_key_examples": dict(list(dupes.items())[:5]),
        "unique_final_retained_records": len(latest),
        "expected_records": len(expected_keys),
        "missing_records": len(missing),
        "missing_examples": [f"{m[0]}|{m[1]}|{m[2]}" for m in list(missing)[:10]],
        "unexpected_records": len(extra),
        "unexpected_examples": [f"{m[0]}|{m[1]}|{m[2]}" for m in list(extra)[:10]],
        "distinct_proteins_covered": len(per_protein_calls),
        "expected_proteins": len(expected_accs),
        "proteins_with_wrong_call_count": len(wrong_count),
        "prompt_ids_used": sorted(prompts_used),
        "p5_present": "P5_selection" in prompts_used,
        "finish_reason_distribution_final": dict(other_finish),
        "truncated_responses_in_final_dataset": len(truncated_final),
        "truncation_retried_count": 0,
        "truncation_replaced_count": 0,
        "truncation_note": (
            "This pipeline's resume logic (load_completed()) marks a key as "
            "done once ANY success=True record exists for it, regardless of "
            "finish_reason. A truncated-but-successful call is therefore "
            "never automatically retried -- identical convention to the "
            "frozen 5-model script and the already-completed GPT-5.5 "
            "script, neither of which retries on truncation either (only "
            "API exceptions, logged success=false, are retry-eligible). "
            "All truncated records were accepted as final on first attempt; "
            "0 were retried, 0 were replaced."
        ),
        "unparseable_retained_records": len(unparseable),
    }

    # ============================================================
    # STEP 2: CLAIM EXTRACTION AUDIT (identical regex/dedup convention to GPT-5.5)
    # ============================================================
    raw_pattern_matches = 0
    dup_go_within_response = 0
    claims_per_call = []
    claim_support = defaultdict(set)  # (acc,ns,go_id) -> {prompt_id, ...}
    zero_claim_calls = 0

    for key, r in latest.items():
        resp = r.get("response", "") or ""
        all_matches = GO_PATTERN.findall(resp)
        raw_pattern_matches += len(all_matches)
        distinct_in_resp = set(all_matches)
        dup_go_within_response += (len(all_matches) - len(distinct_in_resp))
        claims_per_call.append(len(distinct_in_resp))
        if not distinct_in_resp:
            zero_claim_calls += 1
        for go_id in distinct_in_resp:
            claim_support[(key[0], key[1], go_id)].add(key[2])

    final_claims = len(claim_support)
    claims_by_ns = Counter(k[1] for k in claim_support.keys())
    claims_by_org = Counter(org_of.get(k[0], "?") for k in claim_support.keys())
    claims_by_protein = Counter(k[0] for k in claim_support.keys())

    report["claim_extraction"] = {
        "raw_go_pattern_matches_all_calls": raw_pattern_matches,
        "duplicate_go_ids_within_single_responses": dup_go_within_response,
        "final_deduplicated_distinct_claims": final_claims,
        "zero_claim_calls": zero_claim_calls,
        "zero_claim_calls_pct": round(100 * zero_claim_calls / len(latest), 2) if latest else None,
        "claims_per_call_mean": round(float(np.mean(claims_per_call)), 3) if claims_per_call else None,
        "claims_per_call_median": float(np.median(claims_per_call)) if claims_per_call else None,
        "claims_per_protein_mean": round(final_claims / len(claims_by_protein), 2) if claims_by_protein else None,
        "claims_by_namespace": dict(claims_by_ns),
        "claims_by_organism": dict(claims_by_org),
        "distinct_proteins_with_any_claim": len(claims_by_protein),
    }

    with open(out_dir / "parsed_claims.json", "w") as f:
        json.dump({f"{k[0]}|{k[1]}|{k[2]}": sorted(v) for k, v in claim_support.items()}, f)

    # ============================================================
    # STEP 3: CORRECTNESS
    # ============================================================
    rows = []
    for k in claim_support:
        acc, ns, go_id = k
        correct = int(go_id in gt_lookup.get((acc, ns), set()))
        rows.append({"accession": acc, "namespace": ns, "go_id": go_id,
                      "organism": org_of.get(acc, ""), "correct": correct})

    total = len(rows)
    correct_total = sum(r["correct"] for r in rows)
    ns_breakdown = {}
    for ns in NAMESPACES:
        sub = [r for r in rows if r["namespace"] == ns]
        ns_breakdown[ns] = {"n": len(sub), "correct": sum(r["correct"] for r in sub),
                             "precision": round(sum(r["correct"] for r in sub) / len(sub), 4) if sub else None}
    org_breakdown = {}
    for org in ["human", "mouse", "yeast", "ecoli"]:
        sub = [r for r in rows if r["organism"] == org]
        org_breakdown[org] = {"n": len(sub), "correct": sum(r["correct"] for r in sub),
                               "precision": round(sum(r["correct"] for r in sub) / len(sub), 4) if sub else None}

    report["correctness"] = {
        "total_claims": total,
        "correct_claims": correct_total,
        "overall_precision": round(correct_total / total, 4) if total else None,
        "by_namespace": ns_breakdown,
        "by_organism": org_breakdown,
        "open_world_note": "Y=0 means the GO term is not supported by currently available "
                            "experimental annotations for that protein/namespace; it does NOT "
                            "establish that the biological association is false.",
    }

    # ============================================================
    # STEP 4: OVERLAP WITH FROZEN CLAIM SET (read-only lookup, never recomputed)
    # ============================================================
    frozen_scores = json.load(open(FROZEN_SCORE_LOOKUP_PATH))

    for r in rows:
        key_str = f"{r['accession']}|{r['namespace']}|{r['go_id']}"
        score = frozen_scores.get(key_str)
        r["frozen_score"] = score
        r["in_frozen_set"] = score is not None

    in_frozen = [r for r in rows if r["in_frozen_set"]]
    not_in_frozen = [r for r in rows if not r["in_frozen_set"]]
    nf_correct = sum(r["correct"] for r in not_in_frozen)

    report["overlap"] = {
        "total_external_claims": total,
        "overlapping_frozen_claim_set": len(in_frozen),
        "overlapping_pct": round(100 * len(in_frozen) / total, 2) if total else None,
        "external_model_only_claims": len(not_in_frozen),
        "external_only_pct": round(100 * len(not_in_frozen) / total, 2) if total else None,
        "external_only_correct": nf_correct,
        "external_only_precision": round(nf_correct / len(not_in_frozen), 4) if not_in_frozen else None,
        "note": "Only overlapping claims are assigned a frozen score (looked up, never computed "
                "from the external model's own output). External-only claims are reported "
                "descriptively and are never scored.",
    }

    # ============================================================
    # STEP 5: SCORE-CORRECTNESS ANALYSIS (overlapping claims only)
    # ============================================================
    score_table = defaultdict(lambda: {"n": 0, "c": 0})
    for r in in_frozen:
        score_table[r["frozen_score"]]["n"] += 1
        score_table[r["frozen_score"]]["c"] += r["correct"]

    per_score = {}
    for s in range(2, 15):
        d = score_table.get(s, {"n": 0, "c": 0})
        per_score[s] = {"n": d["n"], "c": d["c"],
                         "precision": round(d["c"] / d["n"], 4) if d["n"] else None}

    cumulative = {}
    cum_n, cum_c = 0, 0
    for s in range(14, 1, -1):
        d = score_table.get(s, {"n": 0, "c": 0})
        cum_n += d["n"]; cum_c += d["c"]
        cumulative[s] = {"cum_n": cum_n, "cum_c": cum_c,
                          "cum_precision": round(cum_c / cum_n, 4) if cum_n else None}

    report["score_correctness"] = {"per_score": per_score, "cumulative_at_threshold": cumulative}

    # ============================================================
    # STEP 6: BOOTSTRAP (protein-level, B=2000, seed=42) for every cumulative threshold
    # ============================================================
    bootstrap = {}
    for s in range(2, 15):
        pn = defaultdict(lambda: [0, 0])
        for r in in_frozen:
            if r["frozen_score"] >= s:
                pn[r["accession"]][0] += 1
                pn[r["accession"]][1] += r["correct"]
        res = protein_bootstrap_precision(pn)
        bootstrap[s] = res

    report["bootstrap_by_threshold"] = bootstrap

    # ============================================================
    # STEP 7: ORGANISM / NAMESPACE (overlapping claims, descriptive)
    # ============================================================
    org_overlap = {}
    for org in ["human", "mouse", "yeast", "ecoli"]:
        sub = [r for r in in_frozen if r["organism"] == org]
        org_overlap[org] = {"n": len(sub), "correct": sum(r["correct"] for r in sub),
                             "precision": round(sum(r["correct"] for r in sub) / len(sub), 4) if sub else None,
                             "distinct_proteins": len(set(r["accession"] for r in sub))}
    ns_overlap = {}
    for ns in NAMESPACES:
        sub = [r for r in in_frozen if r["namespace"] == ns]
        ns_overlap[ns] = {"n": len(sub), "correct": sum(r["correct"] for r in sub),
                           "precision": round(sum(r["correct"] for r in sub) / len(sub), 4) if sub else None}

    report["overlap_organism_namespace"] = {"organism": org_overlap, "namespace": ns_overlap,
                                             "descriptive_note": "Descriptive breakdowns of the single "
                                             "external-validation comparison, not independent experiments."}

    out_path = out_dir / "analysis_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {out_path}")
    print(json.dumps({k: v for k, v in report.items() if k in
                       ("integrity", "correctness", "overlap")}, indent=2)[:2000])


if __name__ == "__main__":
    main()
