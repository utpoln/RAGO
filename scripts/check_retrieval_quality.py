"""
check_retrieval_quality.py

Sanity-checks the BLAST retrieval step BEFORE spending any LLM budget:
  - Recall@k: of the ground-truth GO terms for each benchmark protein,
    what fraction appear anywhere in the retrieved candidate list for
    that namespace? This is the retrieval ceiling -- no downstream LLM
    can predict a correct term that was never retrieved.
  - Coverage by organism: does retrieval fail disproportionately for
    any organism (expected to be worse for sparse-literature organisms
    like D. rerio)?

Usage:
    python check_retrieval_quality.py \
        --benchmark_master benchmark_master.json \
        --rag_candidates rag_candidates.json
"""

import argparse
import json
from collections import defaultdict

NAMESPACE_KEY = {
    "MF": "go_molecular_function",
    "BP": "go_biological_process",
    "CC": "go_cellular_component",
}


def parse_gt(field):
    """benchmark_master.json GO fields are '; '-separated 'GO:ID|name' pairs."""
    if not field:
        return set()
    ids = set()
    for chunk in field.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        go_id = chunk.split("|")[0].strip()
        ids.add(go_id)
    return ids


def main(args):
    with open(args.benchmark_master) as f:
        benchmark = json.load(f)
    with open(args.rag_candidates) as f:
        candidates = json.load(f)

    per_ns_recall_num = defaultdict(int)
    per_ns_recall_den = defaultdict(int)
    org_coverage = defaultdict(lambda: {"total": 0, "with_hit": 0})

    instance_level_recalls = []

    for entry in benchmark:
        acc = entry["accession"]
        org = entry["organism"]
        cand = candidates.get(acc, {})
        any_hit = any(len(cand.get(ns, [])) > 0 for ns in ["MF", "BP", "CC"])
        org_coverage[org]["total"] += 1
        if any_hit:
            org_coverage[org]["with_hit"] += 1

        for ns_short, field_name in NAMESPACE_KEY.items():
            gt_ids = parse_gt(entry.get(field_name, ""))
            if not gt_ids:
                continue  # no ground truth in this namespace for this protein
            cand_ids = {c["go_id"] for c in cand.get(ns_short, [])}
            hit = len(gt_ids & cand_ids)
            per_ns_recall_num[ns_short] += hit
            per_ns_recall_den[ns_short] += len(gt_ids)
            instance_level_recalls.append(hit / len(gt_ids))

    print("=" * 60)
    print("RETRIEVAL QUALITY CHECK (ceiling for downstream LLM performance)")
    print("=" * 60)
    print(f"\nRecall@15 by namespace (micro-averaged, term-level):")
    for ns in ["MF", "BP", "CC"]:
        num, den = per_ns_recall_num[ns], per_ns_recall_den[ns]
        pct = 100 * num / den if den else 0.0
        print(f"  {ns}: {num}/{den} ground-truth terms retrieved ({pct:.1f}%)")

    overall_num = sum(per_ns_recall_num.values())
    overall_den = sum(per_ns_recall_den.values())
    print(f"\nOverall micro recall@15: {overall_num}/{overall_den} "
          f"({100*overall_num/overall_den:.1f}%)")
    print(f"Mean per-instance recall@15: "
          f"{100*sum(instance_level_recalls)/len(instance_level_recalls):.1f}% "
          f"(n={len(instance_level_recalls)} protein-namespace instances with ground truth)")

    print(f"\nRetrieval coverage by organism (>=1 BLAST hit in any namespace):")
    for org, d in sorted(org_coverage.items(), key=lambda kv: -kv[1]["with_hit"]/kv[1]["total"]):
        pct = 100 * d["with_hit"] / d["total"]
        print(f"  {org:12s}: {d['with_hit']:4d}/{d['total']:4d} ({pct:.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark_master", default="benchmark_master.json")
    parser.add_argument("--rag_candidates", default="rag_candidates.json")
    args = parser.parse_args()
    main(args)
