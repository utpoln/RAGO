"""
temporal_holdout_rag.py

Temporal-holdout validation for RAGO's "unmatched" predictions, same
methodology as PROBE's temporal_holdout_validation.py: query the
CURRENT UniProt REST API for each sampled accession and check whether
the predicted GO term now appears among that protein's annotations
under any evidence code.

Critical difference from a naive hallucination check: RAGO's candidate
terms are homology-transferred from a DIFFERENT, disjoint pool of
proteins, so an "unmatched" prediction may be a real annotation that
simply has not yet been curated for this specific benchmark protein
as of the Swiss-Prot 2024_03 snapshot used to build the benchmark.
This directly tests that possibility.

Usage:
    python temporal_holdout_rag.py --sample unmatched_sample.csv --output rag_holdout_results.csv
"""

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from collections import Counter

from scipy import stats

EXPERIMENTAL_CODES = {
    "IDA", "IMP", "IPI", "IGI", "IEP", "EXP", "HDA", "HMP", "HGI", "HEP",
}


def fetch_current_uniprot_go(acc, retries=3, sleep_sec=0.15):
    url = f"https://rest.uniprot.org/uniprotkb/{acc}.json"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RAGO-holdout-check/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            entries = []
            for ref in data.get("uniProtKBCrossReferences", []):
                if ref.get("database") != "GO":
                    continue
                evtype = ""
                for prop in ref.get("properties", []):
                    if prop.get("key") == "GoEvidenceType":
                        evtype = prop.get("value", "")
                entries.append({"go_id": ref.get("id"), "evidence": evtype})
            return entries
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5)
        except Exception:
            time.sleep(1.5)
    return None


def clopper_pearson(k, n, alpha=0.05):
    lo = 0.0 if k == 0 else stats.beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(1 - alpha / 2, k + 1, n - k)
    return lo, hi


def main(args):
    rows = list(csv.DictReader(open(args.sample)))
    accessions = sorted({r["accession"] for r in rows})
    print(f"Fetching current UniProt records for {len(accessions)} unique query accessions...")

    cache = {}
    for i, acc in enumerate(accessions):
        cache[acc] = fetch_current_uniprot_go(acc)
        if (i + 1) % 25 == 0:
            print(f"  fetched {i + 1}/{len(accessions)}...")
        time.sleep(0.15)

    results = []
    status_counts = Counter()
    for r in rows:
        acc, ns, go_id = r["accession"], r["namespace"], r["go_id"]
        entries = cache.get(acc)
        status = "protein_not_found" if entries is None else "absent_current"
        evidence = ""
        if entries is not None:
            for e in entries:
                if e["go_id"] == go_id:
                    evidence = e.get("evidence", "")
                    code = evidence.split(":")[0] if evidence else ""
                    status = "present_experimental" if code in EXPERIMENTAL_CODES else "present_non_experimental"
                    break
        results.append({**r, "current_status": status, "current_evidence": evidence})
        status_counts[status] += 1

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["accession", "namespace", "go_id", "current_status", "current_evidence"])
        w.writeheader()
        w.writerows(results)

    total = len(results)
    validated = status_counts["present_experimental"] + status_counts["present_non_experimental"]
    lo, hi = clopper_pearson(validated, total)

    print("\n" + "=" * 60)
    print("RAGO TEMPORAL-HOLDOUT VALIDATION RESULT")
    print("=" * 60)
    for k, v in status_counts.items():
        print(f"  {k:28s}: {v:4d} ({100*v/total:.1f}%)")
    print(f"\n  Validated (any evidence): {validated}/{total} "
          f"({100*validated/total:.2f}%, 95% CI [{100*lo:.2f}%, {100*hi:.2f}%])")
    print(f"\nSaved per-prediction detail to: {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default="unmatched_sample.csv")
    parser.add_argument("--output", default="rag_holdout_results.csv")
    args = parser.parse_args()
    main(args)
