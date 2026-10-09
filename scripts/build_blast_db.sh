#!/bin/bash
# build_blast_db.sh
# Builds a BLAST protein database from the pool FASTA (the 25,460
# non-benchmark proteins ADAPT already carved out).
#
# Usage: bash build_blast_db.sh

set -e

makeblastdb \
  -in pool_proteins.fasta \
  -dbtype prot \
  -out pool_blastdb \
  -title "RAGO pool (non-benchmark) proteins"

echo "BLAST database built: pool_blastdb.*"
