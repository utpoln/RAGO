"""
extract_sequences.py

Single streaming pass over uniprot_sprot.dat to pull amino acid sequences
for two accession sets:
  - "pool" accessions: the 25,460 non-benchmark proteins ADAPT already
    uses for fine-tuning (excludes all 1,000 PROBE benchmark proteins).
    These become the BLAST database we retrieve candidates from.
  - "query" accessions: the 1,000 PROBE benchmark proteins. These are
    BLASTed against the pool database to retrieve homologous candidates.

Usage:
    python extract_sequences.py \
        --dat ../ADAPT/uniprot_sprot.dat \
        --pool_accessions pool_accessions.txt \
        --query_benchmark ../ADAPT/benchmark_master.json \
        --pool_fasta pool_proteins.fasta \
        --query_fasta query_proteins.fasta
"""

import argparse
import json


def load_pool_accessions(path):
    with open(path) as f:
        return {line.strip() for line in f if line.strip()}


def load_query_accessions(benchmark_json):
    with open(benchmark_json) as f:
        data = json.load(f)
    return {d["accession"] for d in data}


def parse_and_extract(dat_file, pool_accs, query_accs, pool_out, query_out):
    stats = {"entries": 0, "pool_found": 0, "query_found": 0}

    pool_f = open(pool_out, "w")
    query_f = open(query_out, "w")

    primary_acc = None
    in_sequence = False
    seq_lines = []

    def flush_entry():
        if primary_acc is None or not seq_lines:
            return
        seq = "".join(seq_lines).replace(" ", "")
        if primary_acc in pool_accs:
            pool_f.write(f">{primary_acc}\n{seq}\n")
            stats["pool_found"] += 1
        if primary_acc in query_accs:
            query_f.write(f">{primary_acc}\n{seq}\n")
            stats["query_found"] += 1

    print(f"Parsing {dat_file} ...")
    with open(dat_file, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            if i % 2_000_000 == 0 and i > 0:
                print(f"  ...{i:,} lines read, {stats['entries']:,} entries, "
                      f"pool={stats['pool_found']:,} query={stats['query_found']:,}")

            if line.startswith("//"):
                flush_entry()
                stats["entries"] += 1
                primary_acc = None
                in_sequence = False
                seq_lines = []
                continue

            if line.startswith("AC") and primary_acc is None:
                # First AC line of the entry; primary accession is the
                # first token before a semicolon.
                val = line[5:].strip()
                primary_acc = val.split(";")[0].strip()
                continue

            if line.startswith("SQ"):
                in_sequence = True
                continue

            if in_sequence and line.startswith("  "):
                # Sequence continuation line, e.g.
                # "     MAFSAEDVLK EYDRRRRMEA ..."
                seq_lines.append(line.strip().replace(" ", ""))
                continue

    pool_f.close()
    query_f.close()

    print("\n" + "=" * 60)
    print("SEQUENCE EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"Total entries parsed:         {stats['entries']:,}")
    print(f"Pool accessions requested:    {len(pool_accs):,}")
    print(f"Pool sequences found:         {stats['pool_found']:,}")
    print(f"Query accessions requested:   {len(query_accs):,}")
    print(f"Query sequences found:        {stats['query_found']:,}")
    if stats["pool_found"] < len(pool_accs):
        print(f"WARNING: {len(pool_accs) - stats['pool_found']} pool accessions "
              f"not found (isoform/secondary-accession mismatch likely).")
    if stats["query_found"] < len(query_accs):
        print(f"WARNING: {len(query_accs) - stats['query_found']} query accessions "
              f"not found (isoform/secondary-accession mismatch likely).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dat", required=True)
    parser.add_argument("--pool_accessions", required=True,
                         help="Text file, one accession per line")
    parser.add_argument("--query_benchmark", required=True,
                         help="PROBE benchmark_master.json")
    parser.add_argument("--pool_fasta", default="pool_proteins.fasta")
    parser.add_argument("--query_fasta", default="query_proteins.fasta")
    args = parser.parse_args()

    pool_accs = load_pool_accessions(args.pool_accessions)
    query_accs = load_query_accessions(args.query_benchmark)
    print(f"Pool accessions to find:  {len(pool_accs):,}")
    print(f"Query accessions to find: {len(query_accs):,}")

    parse_and_extract(args.dat, pool_accs, query_accs, args.pool_fasta, args.query_fasta)
