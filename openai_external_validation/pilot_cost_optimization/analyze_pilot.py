import json, re
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
GO_PATTERN = re.compile(r"GO:\d{7}")

# OpenAI pricing used for gpt-5.5 family (per million tokens) -- recorded explicitly,
# not silently assumed to equal any other model's price. If this cannot be confirmed
# from a pricing endpoint, it is clearly labeled as an assumption below.
PRICE_PER_M = {
    "input_uncached": 5.00,
    "input_cached": 0.50,
    "output": 30.00,  # output/reasoning tokens billed at the output rate
}
PRICING_SOURCE_NOTE = ("Pricing figures: GPT-5.5 standard rates $5.00/M input, $0.50/M cached input, "
                       "$30.00/M output. Confirmed via WebSearch (openai.com/api/pricing returned "
                       "HTTP 403 to direct WebFetch in this session) against multiple independent "
                       "third-party pricing aggregators (apidog.com, promptcost.org, benchlm.ai, "
                       "metacto.com) that converge on identical figures as of Oct 2026 -- not fetched "
                       "directly from OpenAI's own page, flagged as a secondary-source confirmation. "
                       "Batch API cuts ALL rates by 50% per these same sources (not independently "
                       "verified against actual billing data from this session, since the Batch "
                       "object's usage field reports token counts, not dollars).")

results = {}
for name in ["A", "B"]:
    recs = [json.loads(l) for l in open(HERE / "raw" / f"config_{name}_batch_output.jsonl")]
    results[name] = recs

CONFIG_LABEL = {"A": "reasoning_effort=low, max_completion_tokens=4000",
                "B": "reasoning_effort=medium, max_completion_tokens=4000"}

report_data = {}
for name, recs in results.items():
    print("="*90)
    print(f"CONFIGURATION {name}: {CONFIG_LABEL[name]}")
    print("="*90)
    n = len(recs)
    usable, empty, truncated, go_bearing, zero_go, parse_fail = 0,0,0,0,0,0
    go_counts_per_call = []
    input_tokens, cached_tokens, reasoning_tokens, output_tokens = [], [], [], []
    for r in recs:
        body = r["response"]["body"]
        choice = body["choices"][0]
        finish_reason = choice["finish_reason"]
        content = choice["message"]["content"] or ""
        usage = body["usage"]
        input_tokens.append(usage["prompt_tokens"])
        cached_tokens.append(usage["prompt_tokens_details"]["cached_tokens"])
        reasoning_tokens.append(usage["completion_tokens_details"]["reasoning_tokens"])
        output_tokens.append(usage["completion_tokens"])

        go_ids = GO_PATTERN.findall(content)
        go_counts_per_call.append(len(go_ids))

        is_truncated = (finish_reason == "length")
        is_empty = (not content.strip())
        if is_truncated and not go_ids:
            truncated += 1
        if is_empty:
            empty += 1
        if go_ids:
            go_bearing += 1
        elif not is_empty:
            zero_go += 1  # non-empty content but no GO ids parsed (e.g. prose/refusal)
        if not is_truncated and (go_ids or is_empty is False):
            usable += 1
        elif not is_truncated and is_empty:
            # non-truncated empty response -- still "complete" per API but scientifically empty
            usable += 1

    go_arr = np.array(go_counts_per_call)
    print(f"Calls: {n}")
    print(f"Empty visible responses: {empty} ({100*empty/n:.1f}%)")
    print(f"Truncated (finish_reason=length) with no usable GO output: {truncated} ({100*truncated/n:.1f}%)")
    print(f"GO-bearing responses: {go_bearing} ({100*go_bearing/n:.1f}%)")
    print(f"Non-empty, zero-GO-parsed responses (prose/other, not truncated): {zero_go}")
    print(f"Usable scientific responses (not truncated, finish_reason=stop): "
          f"{sum(1 for r in recs if r['response']['body']['choices'][0]['finish_reason']=='stop')}/{n}")
    print(f"GO terms per call: mean={go_arr.mean():.2f} median={np.median(go_arr):.1f} "
          f"min={go_arr.min()} max={go_arr.max()}")
    print(f"Input tokens: mean={np.mean(input_tokens):.1f}  (all identical prompts per protein/ns/prompt; "
          f"total={sum(input_tokens)})")
    print(f"Cached input tokens: mean={np.mean(cached_tokens):.2f}  total={sum(cached_tokens)}  "
          f"(0 confirms caching did NOT engage -- prompts are far under the ~1024-token minimum)")
    print(f"Reasoning tokens: mean={np.mean(reasoning_tokens):.1f} median={np.median(reasoning_tokens):.0f} "
          f"min={min(reasoning_tokens)} max={max(reasoning_tokens)}  total={sum(reasoning_tokens)}")
    print(f"Output tokens (incl. reasoning): mean={np.mean(output_tokens):.1f}  total={sum(output_tokens)}")

    total_input = sum(input_tokens)
    total_cached = sum(cached_tokens)
    total_output = sum(output_tokens)  # includes reasoning tokens, billed at output rate
    uncached_input = total_input - total_cached
    cost_input_uncached = uncached_input/1e6 * PRICE_PER_M["input_uncached"]
    cost_input_cached = total_cached/1e6 * PRICE_PER_M["input_cached"]
    cost_output = total_output/1e6 * PRICE_PER_M["output"]
    total_cost = cost_input_uncached + cost_input_cached + cost_output
    print(f"\nACTUAL PILOT COST (standard, non-Batch-discounted rates):")
    print(f"  uncached input: {uncached_input} tok -> ${cost_input_uncached:.4f}")
    print(f"  cached input:   {total_cached} tok -> ${cost_input_cached:.4f}")
    print(f"  output+reasoning: {total_output} tok -> ${cost_output:.4f}")
    print(f"  TOTAL (48 calls): ${total_cost:.4f}")
    print(f"  Batch discount actually applied to BILLING is not independently verifiable from the")
    print(f"  batch object's 'usage' field alone (it reports token counts, not final $ billed);")
    print(f"  reporting the standard-rate figure above as the reliable baseline, and a 50%-off")
    print(f"  Batch-discount scenario separately below as a labeled assumption, not a verified fact.")
    cost_input_uncached_batch = cost_input_uncached * 0.5
    cost_input_cached_batch = cost_input_cached * 0.5
    cost_output_batch = cost_output * 0.5
    total_cost_batch = cost_input_uncached_batch + cost_input_cached_batch + cost_output_batch
    print(f"  IF a 50% Batch discount applies (standard OpenAI Batch pricing, NOT independently")
    print(f"  confirmed in this session's billing data): ${total_cost_batch:.4f}")

    scale = 2916/48
    proj_mean = total_cost * scale
    proj_batch = total_cost_batch * scale
    max_reasoning = max(reasoning_tokens)
    conservative_output = max_reasoning + int(np.mean([o-r for o,r in zip(output_tokens,reasoning_tokens)]))
    conservative_total_output = conservative_output * 2916
    conservative_cost_output = conservative_total_output/1e6 * PRICE_PER_M["output"]
    conservative_total = (uncached_input/48*2916)/1e6*PRICE_PER_M["input_uncached"] + conservative_cost_output
    print(f"\nPROJECTED COST FOR FULL 2,916-CALL RUN:")
    print(f"  At observed average (standard rate): ${proj_mean:.2f}")
    print(f"  At observed average (if 50% Batch discount applies): ${proj_batch:.2f}")
    print(f"  Conservative (using max observed reasoning_tokens={max_reasoning} per call, standard rate): "
          f"${conservative_total:.2f}")

    report_data[name] = {
        "n": n, "empty": empty, "truncated": truncated, "go_bearing": go_bearing,
        "zero_go_nonempty": zero_go,
        "go_terms_mean": float(go_arr.mean()), "go_terms_median": float(np.median(go_arr)),
        "go_terms_min": int(go_arr.min()), "go_terms_max": int(go_arr.max()),
        "input_tokens_mean": float(np.mean(input_tokens)),
        "cached_tokens_mean": float(np.mean(cached_tokens)),
        "reasoning_tokens_mean": float(np.mean(reasoning_tokens)),
        "reasoning_tokens_median": float(np.median(reasoning_tokens)),
        "reasoning_tokens_max": int(max_reasoning),
        "output_tokens_mean": float(np.mean(output_tokens)),
        "actual_cost_standard": total_cost, "actual_cost_batch_discount_assumed": total_cost_batch,
        "projected_2916_standard": proj_mean, "projected_2916_batch_discount_assumed": proj_batch,
        "projected_2916_conservative": conservative_total,
    }
    print()

with open(HERE / "results" / "pilot_summary.json", "w") as f:
    json.dump({"pricing_note": PRICING_SOURCE_NOTE, "configs": report_data}, f, indent=2)
print("Saved results/pilot_summary.json")
