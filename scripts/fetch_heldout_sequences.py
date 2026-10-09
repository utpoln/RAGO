"""
Step 1: fetch raw sequences for the frozen 243-protein held-out set.
Batched UniProt search (fields=accession,sequence), same pattern already
used successfully for PROBE's 1,000 sequence lengths. No substitution on
failure -- any accession that fails to resolve is reported, not replaced.
"""
import json
import time
import urllib.parse
import urllib.request

with open("/Users/kallolnaha/Documents/mix_projects/mindrouter/RAGO/scripts/heldout_sample_250.json") as f:
    heldout = json.load(f)
accs = [r["accession"] for r in heldout]
assert len(accs) == len(set(accs)) == 243, f"expected 243 unique accessions, got {len(accs)} ({len(set(accs))} unique)"

sequences = {}
BATCH = 100
for i in range(0, len(accs), BATCH):
    batch = accs[i:i+BATCH]
    query = " OR ".join(f"accession:{a}" for a in batch)
    params = {"query": query, "fields": "accession,sequence", "format": "json", "size": "500"}
    url = "https://rest.uniprot.org/uniprotkb/search?" + urllib.parse.urlencode(params)
    data = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RAGO-heldout-seq/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            break
        except Exception as e:
            print(f"retry batch {i}: {e}", flush=True)
            time.sleep(2.0)
    if data is None:
        print(f"BATCH {i}-{i+len(batch)} FAILED ENTIRELY after 5 retries", flush=True)
        continue
    for r in data.get("results", []):
        acc = r["primaryAccession"]
        seq = r.get("sequence", {}).get("value")
        if seq:
            sequences[acc] = seq
    print(f"  batch {i}-{i+len(batch)}: total sequences so far {len(sequences)}", flush=True)

missing = [a for a in accs if a not in sequences]
print(f"\nTotal: {len(sequences)}/{len(accs)} sequences retrieved.")
print(f"Missing: {len(missing)}")
if missing:
    print("MISSING ACCESSIONS (not substituted, reporting only):", missing)

# Verify accession -> exactly one sequence (no duplicate/multi mapping)
dup_check = {}
for a in accs:
    if a in sequences:
        dup_check[a] = dup_check.get(a, 0) + 1
multi = {a: c for a, c in dup_check.items() if c != 1}
print(f"Accessions mapping to != 1 sequence: {len(multi)} {multi if multi else ''}")

with open("/Users/kallolnaha/Documents/mix_projects/mindrouter/RAGO/heldout_query_proteins.fasta", "w") as f:
    for a in accs:
        if a in sequences:
            seq = sequences[a]
            f.write(f">{a}\n")
            for j in range(0, len(seq), 60):
                f.write(seq[j:j+60] + "\n")

with open("/Users/kallolnaha/Documents/mix_projects/mindrouter/RAGO/heldout_sequence_fetch_report.json", "w") as f:
    json.dump({"total_requested": len(accs), "total_retrieved": len(sequences),
               "missing_accessions": missing, "duplicate_mapping_issues": multi}, f, indent=2)

print("\nSaved: heldout_query_proteins.fasta")
print("Saved: heldout_sequence_fetch_report.json")
if missing or multi:
    print("\n*** STOP: sequence retrieval was NOT fully clean. See report above. ***")
else:
    print("\nClean: 243/243 sequences retrieved, each accession maps to exactly 1 sequence.")
