"""
Independent, from-scratch verification of Config A's 48 raw responses.
Does NOT reuse analyze_pilot.py's computed numbers or pilot_summary.json --
re-derives everything directly from raw/config_A_batch_output.jsonl and
raw/config_A_batch_input.jsonl.
"""
import json, re
from pathlib import Path

HERE = Path(__file__).parent
GO_PATTERN = re.compile(r"GO:\d{7}")
GO_LINE_PATTERN = re.compile(r"GO:\d{7}\s*\|\s*\S")  # "GO:XXXXXXX | something" -- the frozen expected format

FROZEN_PROMPTS = {"P1_zeroshot", "P2_constrained", "P3_fewshot", "P4_cot"}
NAMESPACES = {"molecular_function", "biological_process", "cellular_component"}

input_requests = [json.loads(l) for l in open(HERE / "raw" / "config_A_batch_input.jsonl")]
output_records = [json.loads(l) for l in open(HERE / "raw" / "config_A_batch_output.jsonl")]

print(f"Input requests: {len(input_requests)}")
print(f"Output records: {len(output_records)}")

# Build custom_id -> output record map
out_by_id = {r["custom_id"]: r for r in output_records}
in_ids = [r["custom_id"] for r in input_requests]

print("\n" + "="*110)
print("PER-CALL VERIFICATION (all 48)")
print("="*110)
header = f"{'#':>3} {'custom_id':35} {'api_ok':7} {'finish':8} {'nonempty':9} {'out_tok':8} {'n_GO':5} {'parseable':10} {'genuine_fmt':12} {'truncated':10}"
print(header)

rows = []
for i, custom_id in enumerate(sorted(in_ids)):
    rec = out_by_id.get(custom_id)
    if rec is None:
        rows.append({"custom_id": custom_id, "api_ok": False, "missing": True})
        print(f"{i+1:>3} {custom_id:35} MISSING FROM OUTPUT FILE")
        continue
    api_ok = (rec.get("error") is None) and (rec["response"]["status_code"] == 200)
    body = rec["response"]["body"]
    choice = body["choices"][0]
    finish_reason = choice["finish_reason"]
    content = choice["message"]["content"] or ""
    nonempty = bool(content.strip())
    out_tokens = body["usage"]["completion_tokens"]

    # (6) parseable by the exact production GO-extraction logic: GO_PATTERN.findall(content)
    try:
        go_ids = GO_PATTERN.findall(content)
        parseable = True
    except Exception:
        go_ids = []
        parseable = False
    n_go = len(go_ids)

    # (7) genuine GO-annotation-formatted response vs arbitrary text:
    # check each line containing a GO id actually matches "GO:XXXXXXX | term name"
    go_lines = [ln for ln in content.split("\n") if "GO:" in ln]
    genuine_format = all(GO_LINE_PATTERN.search(ln) for ln in go_lines) if go_lines else (n_go == 0)
    # also check there's no obvious off-topic / refusal text pattern
    off_topic_markers = ["i cannot", "i can't", "as an ai", "i'm sorry", "cannot provide"]
    looks_off_topic = any(m in content.lower() for m in off_topic_markers)

    truncated = (finish_reason == "length")

    rows.append({
        "custom_id": custom_id, "api_ok": api_ok, "finish_reason": finish_reason,
        "nonempty": nonempty, "out_tokens": out_tokens, "n_go": n_go,
        "parseable": parseable, "genuine_format": genuine_format and not looks_off_topic,
        "truncated": truncated, "content_preview": content[:80].replace("\n"," / "),
    })
    print(f"{i+1:>3} {custom_id:35} {str(api_ok):7} {finish_reason:8} {str(nonempty):9} "
          f"{out_tokens:8} {n_go:5} {str(parseable):10} {str(genuine_format and not looks_off_topic):12} {str(truncated):10}")

print("\n" + "="*110)
print("CONTENT PREVIEWS (for manual spot-check of 'genuine GO annotation' claim)")
print("="*110)
for r in rows[:10]:
    print(f"{r['custom_id']:35} -> {r.get('content_preview','')}")

print("\n" + "="*110)
print("COMBINATION COMPLETENESS CHECK")
print("="*110)
expected_proteins = {"Q86YC3","P62301","P07347","P76347"}
seen_combos = set()
dup_count = 0
wrong_ns, wrong_prompt, p5_found = [], [], []
for cid in in_ids:
    acc, ns, pid = cid.split("|")
    key = (acc, ns, pid)
    if key in seen_combos:
        dup_count += 1
    seen_combos.add(key)
    if ns not in NAMESPACES:
        wrong_ns.append(cid)
    if pid not in FROZEN_PROMPTS:
        wrong_prompt.append(cid)
    if pid == "P5_selection":
        p5_found.append(cid)

expected_combos = {(a,n,p) for a in expected_proteins for n in NAMESPACES for p in FROZEN_PROMPTS}
missing_combos = expected_combos - seen_combos
extra_combos = seen_combos - expected_combos

print(f"Unique combinations in input file: {len(seen_combos)} (expect 48)")
print(f"Duplicate combinations: {dup_count}")
print(f"Missing combinations: {len(missing_combos)}  {missing_combos if missing_combos else ''}")
print(f"Extra/unexpected combinations: {len(extra_combos)}  {extra_combos if extra_combos else ''}")
print(f"Wrong-namespace entries: {len(wrong_ns)}  {wrong_ns if wrong_ns else ''}")
print(f"Wrong-prompt-id entries: {len(wrong_prompt)}  {wrong_prompt if wrong_prompt else ''}")
print(f"P5 entries found: {len(p5_found)}  {p5_found if p5_found else ''}")

print("\n" + "="*110)
print("DEFINITION: 'scientifically usable response'")
print("="*110)
print("""A response is counted as scientifically usable iff ALL of the following hold:
  (a) the API call succeeded (status_code==200, error is null)
  (b) finish_reason == 'stop' (i.e. the model finished its turn normally, not cut off)
  (c) the response is mechanically parseable by the production GO-extraction regex
      (GO_PATTERN.findall) without raising an exception -- true for any string, so
      this is a non-binding technical check, not a content-quality check
  (d) EVERY line containing the substring 'GO:' matches the expected
      'GO:XXXXXXX | term name' format (no malformed GO-id lines), AND the response
      does not contain an obvious refusal/off-topic marker (e.g. "I cannot", "I'm sorry")
  Zero visible GO ids (a genuine 'no applicable terms' prediction) IS counted as
  scientifically usable as long as (a)-(d) hold -- it is a valid zero-claim prediction,
  not a failure, exactly as in the frozen 5-model primary experiment's convention.""")

print("\n" + "="*110)
print("RECONCILIATION TABLE")
print("="*110)
n_expected = 48
n_api_ok = sum(1 for r in rows if r.get("api_ok"))
n_nonempty = sum(1 for r in rows if r.get("nonempty"))
n_stop = sum(1 for r in rows if r.get("finish_reason") == "stop")
n_length = sum(1 for r in rows if r.get("finish_reason") == "length")
n_go_bearing = sum(1 for r in rows if r.get("n_go", 0) > 0)
n_zero_go = sum(1 for r in rows if r.get("n_go", 0) == 0)
n_parse_fail = sum(1 for r in rows if not r.get("parseable", True))
n_usable = sum(1 for r in rows if r.get("api_ok") and r.get("finish_reason")=="stop" and r.get("parseable") and r.get("genuine_format"))

print(f"| {'Metric':40s} | {'Count':>5} |")
print(f"| {'-'*40} | {'-'*5} |")
print(f"| {'Expected calls':40s} | {n_expected:>5} |")
print(f"| {'API-successful':40s} | {n_api_ok:>5} |")
print(f"| {'Non-empty visible output':40s} | {n_nonempty:>5} |")
print(f"| {'finish_reason=stop':40s} | {n_stop:>5} |")
print(f"| {'finish_reason=length':40s} | {n_length:>5} |")
print(f"| {'GO-bearing responses':40s} | {n_go_bearing:>5} |")
print(f"| {'Zero-GO responses':40s} | {n_zero_go:>5} |")
print(f"| {'Parsing failures':40s} | {n_parse_fail:>5} |")
print(f"| {'Scientifically usable responses':40s} | {n_usable:>5} |")

print(f"\nIs '48/48 scientifically usable' DIRECTLY supported by raw data?: "
      f"{'YES' if n_usable == 48 else f'NO -- only {n_usable}/48 meet the explicit definition above'}")
