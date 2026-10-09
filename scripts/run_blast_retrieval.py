"""
run_blast_retrieval.py

Runs blastp of the 1,000 PROBE benchmark (query) proteins against the
pool BLAST database, then converts hits into per-protein, per-namespace
candidate GO term lists -- the retrieval step of the RAG pipeline.

For each (query protein, namespace), candidate terms are the GO terms
annotated on its top BLAST hits in the pool, ranked by how many
supporting hits they have (ties broken by the best supporting hit's
bit score), truncated to --top_k_terms (default 15, matching PROBE's
P5 candidate-list size for a fair comparison).

Coverage (the fraction of benchmark proteins with >=1 homolog hit above
threshold) is reported explicitly -- this is expected to be incomplete
and should be reported as a limitation, not hidden.

Usage:
    python run_blast_retrieval.py \
        --query_fasta ../query_proteins.fasta \
        --blastdb ../pool_blastdb \
        --pool_go_lookup ../pool_go_lookup.json \
        --benchmark_master ../benchmark_master.json \
        --output ../rag_candidates.json
"""

import argparse
import json
import subprocess
from collections import defaultdict

NAMESPACE_MAP = {
    "molecular_function": "MF",
    "biological_process": "BP",
    "cellular_component": "CC",
}


def run_blast(query_fasta, blastdb, evalue, max_target_seqs, out_tsv):
    cmd = [
        "blastp",
        "-query", query_fasta,
        "-db", blastdb,
        "-evalue", str(evalue),
        "-max_target_seqs", str(max_target_seqs),
        "-outfmt", "6 qseqid sseqid pident length evalue bitscore",
        "-num_threads", "4",
        "-out", out_tsv,
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def parse_blast_hits(tsv_path, top_k_hits):
    """Returns {query_acc: [(subject_acc, bitscore), ...]} truncated to
    top_k_hits per query, sorted by bitscore descending."""
    hits = defaultdict(list)
    with open(tsv_path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            qseqid, sseqid, pident, length, evalue, bitscore = parts
            hits[qseqid].append((sseqid, float(bitscore)))

    truncated = {}
    for q, hit_list in hits.items():
        hit_list.sort(key=lambda x: -x[1])
        truncated[q] = hit_list[:top_k_hits]
    return truncated


def build_candidates(hits_by_query, pool_go_lookup, query_accessions,
                      top_k_terms):
    """For each query accession and namespace, aggregate candidate GO
    terms from its top BLAST hits, ranked by (support count, best
    bit score), truncated to top_k_terms."""
    candidates = {}
    n_with_hits = 0

    for acc in query_accessions:
        hit_list = hits_by_query.get(acc, [])
        candidates[acc] = {}

        for ns_short in ["MF", "BP", "CC"]:
            term_support = defaultdict(lambda: {"count": 0, "best_bitscore": 0.0, "name": ""})
            for subject_acc, bitscore in hit_list:
                for term in pool_go_lookup.get(subject_acc, {}).get(ns_short, []):
                    key = term["go_id"]
                    term_support[key]["count"] += 1
                    term_support[key]["name"] = term["term_name"]
                    term_support[key]["best_bitscore"] = max(
                        term_support[key]["best_bitscore"], bitscore
                    )

            ranked = sorted(
                term_support.items(),
                key=lambda kv: (-kv[1]["count"], -kv[1]["best_bitscore"]),
            )[:top_k_terms]

            candidates[acc][ns_short] = [
                {"go_id": go_id, "term_name": info["name"]}
                for go_id, info in ranked
            ]

        if hit_list:
            n_with_hits += 1

    coverage = n_with_hits / len(query_accessions) if query_accessions else 0.0
    return candidates, coverage, n_with_hits


def main(args):
    run_blast(args.query_fasta, args.blastdb, args.evalue,
              args.max_target_seqs, args.blast_tsv)

    hits_by_query = parse_blast_hits(args.blast_tsv, args.top_k_hits)

    with open(args.pool_go_lookup) as f:
        pool_go_lookup = json.load(f)

    with open(args.benchmark_master) as f:
        benchmark = json.load(f)
    query_accessions = [d["accession"] for d in benchmark]

    candidates, coverage, n_with_hits = build_candidates(
        hits_by_query, pool_go_lookup, query_accessions, args.top_k_terms
    )

    with open(args.output, "w") as f:
        json.dump(candidates, f)

    print("\n" + "=" * 60)
    print("RAG RETRIEVAL (BLAST) SUMMARY")
    print("=" * 60)
    print(f"Query proteins:               {len(query_accessions):,}")
    print(f"Query proteins with >=1 hit:  {n_with_hits:,} ({100*coverage:.1f}% coverage)")
    print(f"Query proteins with NO hit:   {len(query_accessions) - n_with_hits:,}")
    print(f"BLAST e-value threshold:      {args.evalue}")
    print(f"Top-k hits used per query:    {args.top_k_hits}")
    print(f"Top-k candidate terms/ns:     {args.top_k_terms}")
    print(f"Saved candidates to:          {args.output}")
    print("\nNOTE: proteins with no BLAST hit above threshold get an empty")
    print("candidate list for that namespace. Report this coverage figure")
    print("explicitly in the paper -- do not silently fall back without")
    print("disclosing it, since it changes what the RAG condition means.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query_fasta", default="query_proteins.fasta")
    parser.add_argument("--blastdb", default="pool_blastdb")
    parser.add_argument("--pool_go_lookup", default="pool_go_lookup.json")
    parser.add_argument("--benchmark_master", default="benchmark_master.json")
    parser.add_argument("--output", default="rag_candidates.json")
    parser.add_argument("--blast_tsv", default="blast_hits.tsv")
    parser.add_argument("--evalue", type=float, default=1e-5)
    parser.add_argument("--max_target_seqs", type=int, default=50)
    parser.add_argument("--top_k_hits", type=int, default=10,
                         help="Number of top BLAST hits to pool GO terms from")
    parser.add_argument("--top_k_terms", type=int, default=15,
                         help="Final candidate list size per namespace "
                              "(15 matches PROBE's P5 format for direct comparison)")
    args = parser.parse_args()
    main(args)
