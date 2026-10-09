"""
build_pool_go_lookup.py

Consolidates ADAPT's training_data.jsonl (one row per protein x namespace)
into a single accession -> {namespace: [{go_id, term_name}, ...]} lookup,
used to map BLAST hit accessions to their candidate GO terms during
retrieval.

Usage:
    python build_pool_go_lookup.py \
        --training_data ../ADAPT/training_data.jsonl \
        --output pool_go_lookup.json
"""

import argparse
import json
from collections import defaultdict


def main(training_data_path, output_path):
    lookup = defaultdict(lambda: {"MF": [], "BP": [], "CC": []})

    with open(training_data_path) as f:
        for line in f:
            rec = json.loads(line)
            acc = rec["accession"]
            ns = rec["namespace"]
            lookup[acc][ns] = rec["go_terms"]  # [{"go_id":..., "term_name":...}, ...]

    with open(output_path, "w") as f:
        json.dump(lookup, f)

    print(f"Pool GO lookup built for {len(lookup):,} accessions -> {output_path}")
    total_terms = sum(len(v) for entry in lookup.values() for v in entry.values())
    print(f"Total (accession, namespace, term) entries: {total_terms:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--training_data", default="../ADAPT/training_data.jsonl")
    parser.add_argument("--output", default="pool_go_lookup.json")
    args = parser.parse_args()
    main(args.training_data, args.output)
