"""
qwen3_truncation_sensitivity.py

A read-only sensitivity audit of the 404 Qwen3 32B responses with
finish_reason="length". Does NOT modify the raw Qwen3 JSONL, does NOT
touch the frozen five-model files or GPT-5.5, does NOT rerun anything,
does NOT delete any record. Reuses the exact same GO-pattern regex,
ground-truth source, frozen-score lookup, and bootstrap procedure as
analyze_external_model.py / the GPT-5.5 analysis -- no new statistical
method, no new claim definition.
"""

import json
import re
from pathlib import Path
from collections import defaultdict, Counter

import numpy as np

HERE = Path(__file__).resolve().parent
RAGO = HERE.parent
GO_PATTERN = re.compile(r"GO:\d{7}")
FROZEN_SCORE_LOOKUP_PATH = RAGO / "openai_external_validation" / "analysis" / "frozen_claim_score_lookup_READONLY.json"
B_BOOTSTRAP, SEED = 2000, 42

heldout = json.load(open(RAGO / "scripts" / "heldout_sample_250.json"))
org_of = {r["accession"]: r["organism"] for r in heldout}
gt_lookup = {}
for r in heldout:
    for ns_full, ns_short in [("molecular_function", "MF"), ("biological_process", "BP"), ("cellular_component", "CC")]:
        gt_lookup[(r["accession"], ns_full)] = set(t["go_id"] for t in r["go_terms"].get(ns_short, []))

frozen_scores = json.load(open(FROZEN_SCORE_LOOKUP_PATH))


def bootstrap_ci(per_protein_nc, B=B_BOOTSTRAP, seed=SEED):
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
    return {"point": total_c / total_n if total_n else None, "ci_lo": float(lo), "ci_hi": float(hi), "n_proteins": N}


def build_claims(records):
    """records: list of raw dicts (one per retained call). Returns claim_support
    dict (acc,ns,go_id)->set(prompt_ids), using identical regex/dedup convention."""
    claim_support = defaultdict(set)
    zero = 0
    for r in records:
        resp = r.get("response", "") or ""
        found = set(GO_PATTERN.findall(resp))
        if not found:
            zero += 1
        for go_id in found:
            claim_support[(r["accession"], r["namespace"], go_id)].add(r["prompt_id"])
    return claim_support, zero


def score_claims(claim_support):
    rows = []
    for (acc, ns, go_id) in claim_support:
        correct = int(go_id in gt_lookup.get((acc, ns), set()))
        key_str = f"{acc}|{ns}|{go_id}"
        score = frozen_scores.get(key_str)
        rows.append({"accession": acc, "namespace": ns, "go_id": go_id, "correct": correct,
                      "frozen_score": score, "in_frozen_set": score is not None})
    return rows


def cumulative_table(in_frozen_rows):
    score_table = defaultdict(lambda: {"n": 0, "c": 0})
    for r in in_frozen_rows:
        score_table[r["frozen_score"]]["n"] += 1
        score_table[r["frozen_score"]]["c"] += r["correct"]
    cum = {}
    cum_n, cum_c = 0, 0
    for s in range(14, 1, -1):
        d = score_table.get(s, {"n": 0, "c": 0})
        cum_n += d["n"]; cum_c += d["c"]
        cum[s] = {"cum_n": cum_n, "cum_c": cum_c, "cum_precision": round(cum_c / cum_n, 4) if cum_n else None}
    return cum, score_table


def bootstrap_at(in_frozen_rows, threshold):
    pn = defaultdict(lambda: [0, 0])
    for r in in_frozen_rows:
        if r["frozen_score"] >= threshold:
            pn[r["accession"]][0] += 1
            pn[r["accession"]][1] += r["correct"]
    return bootstrap_ci(pn)


def main():
    raw = [json.loads(l) for l in open(HERE / "qwen3_32b" / "Qwen_Qwen3-32B.jsonl")]
    latest = {}
    for r in raw:
        key = (r["accession"], r["namespace"], r["prompt_id"])
        if r.get("success"):
            latest[key] = r
    all_records = list(latest.values())
    assert len(all_records) == 2916

    truncated = [r for r in all_records if r.get("finish_reason") == "length"]
    non_truncated = [r for r in all_records if r.get("finish_reason") != "length"]
    assert len(truncated) == 404
    assert len(non_truncated) == 2512

    report = {}

    # ================= 1. Characterize the 404 truncated responses =================
    n_with_go = sum(1 for r in truncated if GO_PATTERN.search(r.get("response", "") or ""))
    n_zero_go = len(truncated) - n_with_go
    trunc_claims, trunc_zero = build_claims(truncated)
    trunc_rows = score_claims(trunc_claims)
    trunc_correct = sum(r["correct"] for r in trunc_rows)
    trunc_in_frozen = [r for r in trunc_rows if r["in_frozen_set"]]
    trunc_score_dist = Counter(r["frozen_score"] for r in trunc_in_frozen)
    trunc_ge = {s: sum(1 for r in trunc_in_frozen if r["frozen_score"] >= s) for s in (9, 12, 14)}

    report["part1_truncated_characterization"] = {
        "n_truncated_responses": len(truncated),
        "n_with_at_least_one_go_term": n_with_go,
        "n_with_zero_go_terms": n_zero_go,
        "deduplicated_claims_from_truncated_responses": len(trunc_claims),
        "correct_claims_from_truncated_responses": trunc_correct,
        "descriptive_precision_truncated_origin_claims": round(trunc_correct / len(trunc_claims), 4) if trunc_claims else None,
        "truncated_claims_overlapping_frozen_set": len(trunc_in_frozen),
        "truncated_claims_overlap_pct": round(100 * len(trunc_in_frozen) / len(trunc_claims), 2) if trunc_claims else None,
        "truncated_overlapping_claims_by_score": {str(s): trunc_score_dist.get(s, 0) for s in range(2, 15)},
        "truncated_overlapping_claims_ge9": trunc_ge[9],
        "truncated_overlapping_claims_ge12": trunc_ge[12],
        "truncated_overlapping_claims_ge14": trunc_ge[14],
    }

    # ================= 7. Token / completeness inspection =================
    comp_trunc = [r["usage"].get("completion_tokens") for r in truncated if r.get("usage")]
    comp_nontrunc = [r["usage"].get("completion_tokens") for r in non_truncated if r.get("usage")]
    report["part7_token_inspection"] = {
        "truncated_completion_tokens": {
            "min": min(comp_trunc), "max": max(comp_trunc),
            "mean": round(float(np.mean(comp_trunc)), 1), "median": float(np.median(comp_trunc)),
        } if comp_trunc else None,
        "non_truncated_completion_tokens": {
            "min": min(comp_nontrunc), "max": max(comp_nontrunc),
            "mean": round(float(np.mean(comp_nontrunc)), 1), "median": float(np.median(comp_nontrunc)),
        } if comp_nontrunc else None,
        "max_tokens_budget": 512,
        "note": ("Qwen3-32B is a reasoning model; extract_response_content() already strips "
                 "<think>...</think> blocks and falls back to reasoning_content when content "
                 "is empty, identically to the frozen pipeline's established handling. "
                 "n_with_zero_go_terms among truncated responses indicates the cutoff landed "
                 "before any GO term was emitted (reasoning likely consumed the full budget); "
                 "n_with_at_least_one_go_term indicates at least partial answer content survived."),
    }

    # sample a few truncated responses' tail content for qualitative inspection
    samples = []
    for r in truncated[:3]:
        resp = r.get("response", "") or ""
        samples.append({"accession": r["accession"], "namespace": r["namespace"], "prompt_id": r["prompt_id"],
                         "completion_tokens": r.get("usage", {}).get("completion_tokens"),
                         "has_go_term": bool(GO_PATTERN.search(resp)),
                         "tail_200_chars": resp[-200:]})
    report["part7_samples"] = samples

    # ================= 2/3. Dataset A (full, reuse already-saved report) vs Dataset B (exclude truncated) =================
    full_report = json.load(open(HERE / "qwen3_32b" / "analysis_report.json"))
    datasetA = {
        "claims": full_report["correctness"]["total_claims"],
        "correct": full_report["correctness"]["correct_claims"],
        "overall_precision": full_report["correctness"]["overall_precision"],
        "overlap_n": full_report["overlap"]["overlapping_frozen_claim_set"],
        "score_ge9": full_report["score_correctness"]["cumulative_at_threshold"]["9"]["cum_precision"],
        "score_ge12": full_report["score_correctness"]["cumulative_at_threshold"]["12"]["cum_precision"],
        "score_ge14": full_report["score_correctness"]["cumulative_at_threshold"]["14"]["cum_precision"],
        "bootstrap_ge9": full_report["bootstrap_by_threshold"]["9"],
        "bootstrap_ge12": full_report["bootstrap_by_threshold"]["12"],
        "bootstrap_ge14": full_report["bootstrap_by_threshold"]["14"],
    }

    nt_claims, nt_zero = build_claims(non_truncated)
    nt_rows = score_claims(nt_claims)
    nt_total = len(nt_rows)
    nt_correct = sum(r["correct"] for r in nt_rows)
    nt_in_frozen = [r for r in nt_rows if r["in_frozen_set"]]
    nt_cum, _ = cumulative_table(nt_in_frozen)
    nt_bootstrap = {s: bootstrap_at(nt_in_frozen, s) for s in (9, 12, 14)}

    datasetB = {
        "claims": nt_total,
        "correct": nt_correct,
        "overall_precision": round(nt_correct / nt_total, 4) if nt_total else None,
        "overlap_n": len(nt_in_frozen),
        "score_ge9": nt_cum[9]["cum_precision"],
        "score_ge12": nt_cum[12]["cum_precision"],
        "score_ge14": nt_cum[14]["cum_precision"],
        "bootstrap_ge9": nt_bootstrap[9],
        "bootstrap_ge12": nt_bootstrap[12],
        "bootstrap_ge14": nt_bootstrap[14],
    }

    report["datasetA_full_2916"] = datasetA
    report["datasetB_exclude_404_truncated"] = datasetB

    def pct_diff(a, b):
        if a is None or b is None:
            return None
        return round(b - a, 4)

    report["comparison"] = {
        "claims_diff": datasetB["claims"] - datasetA["claims"],
        "correct_diff": datasetB["correct"] - datasetA["correct"],
        "overall_precision_diff_pp": pct_diff(datasetA["overall_precision"], datasetB["overall_precision"]),
        "score_ge9_diff_pp": pct_diff(datasetA["score_ge9"], datasetB["score_ge9"]),
        "score_ge12_diff_pp": pct_diff(datasetA["score_ge12"], datasetB["score_ge12"]),
        "score_ge14_diff_pp": pct_diff(datasetA["score_ge14"], datasetB["score_ge14"]),
    }

    with open(HERE / "qwen3_32b" / "truncation_sensitivity_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
