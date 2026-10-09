"""
decompose_rag_unmatched.py

Decomposes RAGO's "unmatched" rate (HR) into failure modes, analogous to
PROBE's hallucination_decompose.py, but adapted for the selection-task
structure: since the model is asked to pick from a provided candidate
list (not generate freely), there is an extra, RAGO-specific category
to check first -- did the model even stay within the offered candidates?

Categories (in order of severity):
  (a) off-list:        predicted GO ID is NOT in the candidate list we
                        offered -- true generation-level non-compliance,
                        the closest analogue to PROBE's "hallucination."
  (b) syntactic:        predicted GO ID is on-list but not a real GO ID
                        (should be ~0, since candidates are sourced from
                        real curated annotations).
  (c) unmatched:        predicted GO ID is on-list, valid, but does not
                        match this specific protein's own ground truth.
                        This is the bucket that needs temporal-holdout
                        validation -- it may be a real annotation
                        correctly transferred from a homolog but simply
                        absent from this small benchmark's curated
                        ground truth, not necessarily wrong.

Usage:
    python decompose_rag_unmatched.py \
        --results_dir rag_results \
        --go_obo go-basic.obo \
        --output unmatched_sample.csv
"""

import argparse
import json
import re
import random
from pathlib import Path
from collections import Counter

GO_PATTERN = re.compile(r"GO:\d{7}")


def load_valid_go_ids(obo_path):
    valid = set()
    with open(obo_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("id: GO:"):
                valid.add(line.replace("id: ", "").strip())
    return valid


def main(args):
    valid_go_ids = load_valid_go_ids(args.go_obo) if args.go_obo else None

    counts = Counter()
    unmatched_rows = []  # (accession, namespace, go_id, model)

    results_dir = Path(args.results_dir)
    for fp in results_dir.glob("*.jsonl"):
        model = fp.stem
        with open(fp) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not rec.get("success", False) or rec.get("no_retrieval", False):
                    continue

                candidate_ids = set()
                # Recover candidate IDs from the prompt text (it lists them).
                prompt = rec.get("prompt_text", "")
                if prompt:
                    candidate_ids = set(GO_PATTERN.findall(prompt))

                ground_truth = set(GO_PATTERN.findall(rec.get("ground_truth", "") or ""))
                predicted = set(GO_PATTERN.findall(rec.get("response", "") or ""))

                for go_id in predicted:
                    counts["total_predicted"] += 1
                    if go_id in ground_truth:
                        counts["correct"] += 1
                        continue
                    if candidate_ids and go_id not in candidate_ids:
                        counts["off_list"] += 1
                        continue
                    if valid_go_ids is not None and go_id not in valid_go_ids:
                        counts["syntactic"] += 1
                        continue
                    counts["unmatched"] += 1
                    unmatched_rows.append(
                        (rec["accession"], rec["namespace"], go_id, model)
                    )

    print("=" * 60)
    print("RAGO UNMATCHED-RATE DECOMPOSITION (pilot data)")
    print("=" * 60)
    total = counts["total_predicted"]
    for k in ["correct", "off_list", "syntactic", "unmatched"]:
        n = counts[k]
        print(f"  {k:12s}: {n:5d} ({100*n/total:.1f}% of {total} total predictions)")

    # Sample for temporal-holdout validation
    random.seed(42)
    unique_rows = list({(a, n, g) for a, n, g, m in unmatched_rows})
    print(f"\nUnique (accession, namespace, go_id) unmatched tuples: {len(unique_rows)}")
    sample = random.sample(unique_rows, min(args.n_sample, len(unique_rows)))

    with open(args.output, "w") as f:
        f.write("accession,namespace,go_id\n")
        for acc, ns, go_id in sample:
            f.write(f"{acc},{ns},{go_id}\n")
    print(f"Sampled {len(sample)} unmatched tuples -> {args.output}")
    print("(Note: 'accession' here is the QUERY protein -- we check whether")
    print(" the predicted term now applies to the benchmark protein itself,")
    print(" not the homolog it was retrieved from.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results_dir", default="rag_results")
    parser.add_argument("--go_obo", default=None,
                         help="Path to go-basic.obo (optional, for syntactic check)")
    parser.add_argument("--output", default="unmatched_sample.csv")
    parser.add_argument("--n_sample", type=int, default=120)
    args = parser.parse_args()
    main(args)
