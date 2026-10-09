"""
draw_heldout_sample.py

Draws the final N=250 held-out confirmatory benchmark, per the approved
design:
  - 4 organisms (zebrafish excluded: 0% empirical yield in feasibility
    testing -- its eligible Swiss-Prot pool was already essentially
    exhausted by PROBE+ADAPT), equal allocation: 63/63/62/62.
  - Source pool: reviewed Swiss-Prot entries NOT in PROBE's 1,000
    benchmark proteins and NOT in ADAPT's 25,460 training pool.
  - Qualification: >=3 experimental-evidence GO terms (current UniProt
    state) AND non-empty FUNCTION comment (same bar PROBE/ADAPT used).
  - Procedure: full accession-ID enumeration per organism -> exclude
    touched -> shuffle (documented seed) -> sequentially check
    qualification in that fixed random order -> keep first N_target
    qualifiers. This is a legitimate simple random sample from the
    eligible population (not adaptive/cherry-picked): every candidate
    is checked in a pre-fixed random order, and every checked candidate
    (qualifying or not) is logged for auditability.

Usage:
    python draw_heldout_sample.py
"""
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BATCH_SIZE = 20   # candidates fetched concurrently per round
MAX_WORKERS = 8   # modest concurrency -- still a respectful rate against a public API

SEED = 42
TARGETS = {"human": 63, "mouse": 63, "yeast": 62, "ecoli": 62}
TAXON = {"human": "9606", "mouse": "10090", "yeast": "559292", "ecoli": "83333"}
# Fixed processing order -- part of the documented, reproducible procedure
ORGANISM_ORDER = ["human", "mouse", "yeast", "ecoli"]

EXPERIMENTAL_CODES = {"IDA", "IMP", "IPI", "IGI", "IEP", "EXP", "HDA", "HMP", "HGI", "HEP"}


def load_touched():
    with open("/Users/kallolnaha/Documents/mix_projects/mindrouter/ADAPT/benchmark_master.json") as f:
        probe_1000 = {d["accession"] for d in json.load(f)}
    adapt_pool = set()
    with open("/Users/kallolnaha/Documents/mix_projects/mindrouter/ADAPT/training_data.jsonl") as f:
        for line in f:
            adapt_pool.add(json.loads(line)["accession"])
    return probe_1000 | adapt_pool


def fetch_all_accessions(taxon_id):
    """Paginate through UniProt search results to get every reviewed
    accession for this organism (IDs only -- cheap)."""
    accs = []
    base = "https://rest.uniprot.org/uniprotkb/search"
    params = {
        "query": f"organism_id:{taxon_id} AND reviewed:true",
        "format": "json",
        "size": "500",
        "fields": "accession",
    }
    url = base + "?" + urllib.parse.urlencode(params)
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "RAGO-heldout-draw/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            link_header = resp.headers.get("Link", "")
        accs.extend(r["primaryAccession"] for r in data.get("results", []))
        # parse next cursor from Link header: <url>; rel="next"
        next_url = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().lstrip("<").rstrip(">")
        url = next_url
        time.sleep(0.1)
    return accs


def fetch_entry(acc):
    url = f"https://rest.uniprot.org/uniprotkb/{acc}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "RAGO-heldout-draw/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    return None


def count_experimental_go(entry):
    counts = {"MF": 0, "BP": 0, "CC": 0}
    ns_map = {"F": "MF", "P": "BP", "C": "CC"}
    for ref in entry.get("uniProtKBCrossReferences", []):
        if ref.get("database") != "GO":
            continue
        goterm_val, evtype = "", ""
        for prop in ref.get("properties", []):
            if prop.get("key") == "GoTerm":
                goterm_val = prop.get("value", "")
            if prop.get("key") == "GoEvidenceType":
                evtype = prop.get("value", "")
        code = evtype.split(":")[0] if evtype else ""
        if code in EXPERIMENTAL_CODES and goterm_val:
            ns = ns_map.get(goterm_val[0])
            if ns:
                counts[ns] += 1
    return counts


def has_function_text(entry):
    return any(c.get("commentType") == "FUNCTION" for c in entry.get("comments", []))


def extract_fields(entry, acc, organism_label):
    go_counts = count_experimental_go(entry)
    func_text = ""
    for c in entry.get("comments", []):
        if c.get("commentType") == "FUNCTION":
            texts = c.get("texts", [])
            if texts:
                func_text = texts[0].get("value", "")
            break
    gene_name = ""
    genes = entry.get("genes", [])
    if genes:
        gene_name = genes[0].get("geneName", {}).get("value", "")
    protein_name = entry.get("proteinDescription", {}).get("recommendedName", {}) \
        .get("fullName", {}).get("value", "")
    organism_full = entry.get("organism", {}).get("scientificName", "")
    seq_length = entry.get("sequence", {}).get("length")

    # Collect GO terms with evidence, per namespace, for ground truth
    go_terms = {"MF": [], "BP": [], "CC": []}
    ns_map = {"F": "MF", "P": "BP", "C": "CC"}
    for ref in entry.get("uniProtKBCrossReferences", []):
        if ref.get("database") != "GO":
            continue
        go_id, goterm_val, evtype = ref.get("id"), "", ""
        for prop in ref.get("properties", []):
            if prop.get("key") == "GoTerm":
                goterm_val = prop.get("value", "")
            if prop.get("key") == "GoEvidenceType":
                evtype = prop.get("value", "")
        code = evtype.split(":")[0] if evtype else ""
        if code in EXPERIMENTAL_CODES and goterm_val:
            ns = ns_map.get(goterm_val[0])
            if ns:
                go_terms[ns].append({"go_id": go_id, "term_name": goterm_val[2:], "evidence": code})

    return {
        "accession": acc,
        "organism": organism_label,
        "organism_full": organism_full,
        "gene_name": gene_name,
        "protein_name": protein_name,
        "function_text": func_text,
        "sequence_length": seq_length,
        "n_exp_go_mf": go_counts["MF"],
        "n_exp_go_bp": go_counts["BP"],
        "n_exp_go_cc": go_counts["CC"],
        "n_exp_go_total": sum(go_counts.values()),
        "go_terms": go_terms,
    }


def main():
    touched = load_touched()
    print(f"Touched (excluded) accessions: {len(touched):,}\n", flush=True)

    rng = random.Random(SEED)
    final_sample = []
    audit_log = []  # every candidate checked, in order, with outcome
    eligible_pools = {}  # org -> full fresh (untouched) candidate list, for auditability

    for org in ORGANISM_ORDER:
        target = TARGETS[org]
        taxon = TAXON[org]
        print(f"=== {org} (taxon {taxon}), target={target} ===", flush=True)

        all_accs = fetch_all_accessions(taxon)
        print(f"  Total reviewed accessions: {len(all_accs):,}", flush=True)
        fresh = [a for a in all_accs if a not in touched]
        print(f"  Fresh (untouched): {len(fresh):,}", flush=True)
        eligible_pools[org] = sorted(fresh)

        shuffled = fresh[:]
        rng.shuffle(shuffled)

        # Fetch in fixed-order batches, each batch fetched concurrently, but
        # results are only ever consumed in the pre-shuffled order -- a
        # candidate's qualification never depends on fetch timing/races, so
        # parallelism changes wall-clock time only, not which proteins are
        # selected (the pre-registered selection rule is unaffected).
        qualified_this_org = []
        n_checked = 0
        pos = 0
        t_start = time.time()
        while pos < len(shuffled) and len(qualified_this_org) < target:
            batch = shuffled[pos: pos + BATCH_SIZE]
            pos += BATCH_SIZE
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                entries = list(ex.map(fetch_entry, batch))
            for acc, entry in zip(batch, entries):
                if len(qualified_this_org) >= target:
                    break
                n_checked += 1
                if entry is None:
                    audit_log.append({"accession": acc, "organism": org, "qualifies": False,
                                       "reason": "fetch_failed_or_404"})
                    continue
                go_counts = count_experimental_go(entry)
                total_exp = sum(go_counts.values())
                func_ok = has_function_text(entry)
                qualifies = total_exp >= 3 and func_ok
                audit_log.append({"accession": acc, "organism": org, "qualifies": qualifies,
                                   "n_exp_go": total_exp, "has_function_text": func_ok})
                if qualifies:
                    record = extract_fields(entry, acc, org)
                    qualified_this_org.append(record)
            elapsed = time.time() - t_start
            print(f"    ...checked {n_checked} so far, qualified {len(qualified_this_org)}/{target} "
                  f"({elapsed:.0f}s elapsed)", flush=True)

        print(f"  Checked {n_checked} candidates (in pre-shuffled order) to find {len(qualified_this_org)} "
              f"qualifying (target {target})\n", flush=True)
        final_sample.extend(qualified_this_org)

    print(f"\nFinal held-out sample: {len(final_sample)} proteins", flush=True)
    for org in ORGANISM_ORDER:
        n = sum(1 for r in final_sample if r["organism"] == org)
        print(f"  {org}: {n}", flush=True)

    with open("heldout_sample_250.json", "w") as f:
        json.dump(final_sample, f, indent=2)
    with open("heldout_draw_audit_log.json", "w") as f:
        json.dump({"seed": SEED, "targets": TARGETS, "organism_order": ORGANISM_ORDER,
                    "eligible_pool_sizes": {o: len(v) for o, v in eligible_pools.items()},
                    "eligible_pools": eligible_pools,
                    "log": audit_log}, f, indent=2)
    print("\nSaved: heldout_sample_250.json", flush=True)
    print("Saved: heldout_draw_audit_log.json (every candidate checked + full eligible pool per organism, for auditability)", flush=True)


if __name__ == "__main__":
    main()
