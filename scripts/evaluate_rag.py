"""
evaluate_rag.py

Scores RAGO's rag_results/*.jsonl using the identical convention as
PROBE's evaluation.py: every protein x namespace pair is included in
the macro-average, scoring 0 for pairs lacking an experimental
annotation in that namespace (NOT skipped), so RAG's F1 is directly
comparable to PROBE's P1-P5 leaderboard and ADAPT's numbers (once
those exist) without any convention mismatch.

Usage:
    python evaluate_rag.py --results_dir rag_results --output_dir rag_evaluation
"""

import re
import json
import argparse
from pathlib import Path
from collections import defaultdict

GO_PATTERN = re.compile(r"GO:\d{7}")

MODEL_DISPLAY = {
    "llama3.1:8b": "Llama 3.1 8B", "llama3.3:70b": "Llama 3.3 70B",
    "mistral:7b": "Mistral 7B", "mistral-large:123b": "Mistral Large 123B",
    "qwen2.5:7b": "Qwen2.5 7B", "qwen2.5:72b": "Qwen2.5 72B",
    "Qwen/Qwen3-32B": "Qwen3 32B", "gemma3:12b": "Gemma3 12B",
    "google/gemma-4-31b": "Gemma-4 31B", "mixtral:8x7b": "Mixtral 8x7B",
}

# PROBE's own P5 (fixed global candidate list) leaderboard, for reference.
# From the published PROBE paper, Table 9 (P5 column).
PROBE_P5_F1 = {
    "Mistral Large 123B": 0.099, "Llama 3.3 70B": 0.095, "Qwen2.5 72B": 0.090,
    "Qwen3 32B": 0.066, "Gemma-4 31B": 0.100, "Llama 3.1 8B": 0.079,
    "Mixtral 8x7B": 0.087, "Qwen2.5 7B": 0.066, "Mistral 7B": 0.062,
    "Gemma3 12B": 0.075,
}


def parse_go(text):
    return set(GO_PATTERN.findall(text or ""))


def compute_metrics(predicted, ground_truth):
    if not ground_truth:
        return 0.0, 0.0, 0.0
    tp = len(predicted & ground_truth)
    fp = len(predicted - ground_truth)
    fn = len(ground_truth - predicted)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return prec, rec, f1


def build_reference_set(results_dir):
    """Union of all ground-truth GO IDs, for hallucination/unmatched-rate scoring."""
    R = set()
    for fp in results_dir.glob("*.jsonl"):
        with open(fp) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    R.update(parse_go(rec.get("ground_truth", "")))
                except Exception:
                    continue
    return R


def evaluate_model(filepath, ref_set):
    precs, recs, f1s, hr_vals, n_vals = [], [], [], [], []
    by_ns = defaultdict(lambda: {"precs": [], "recs": [], "f1s": []})
    n_no_retrieval = 0
    n_total = 0

    with open(filepath) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not rec.get("success", False):
                continue
            n_total += 1
            if rec.get("no_retrieval", False):
                n_no_retrieval += 1

            predicted = parse_go(rec.get("response", ""))
            ground_truth = parse_go(rec.get("ground_truth", ""))
            prec, rec_, f1 = compute_metrics(predicted, ground_truth)
            precs.append(prec)
            recs.append(rec_)
            f1s.append(f1)

            n_pred = len(predicted)
            hallucinated = predicted - ref_set
            hr = len(hallucinated) / n_pred if n_pred > 0 else 0.0
            hr_vals.append(hr)
            n_vals.append(n_pred)

            ns = rec.get("namespace", "")
            by_ns[ns]["precs"].append(prec)
            by_ns[ns]["recs"].append(rec_)
            by_ns[ns]["f1s"].append(f1)

    n = len(f1s)
    if n == 0:
        return None

    result = {
        "n": n,
        "n_no_retrieval": n_no_retrieval,
        "pct_no_retrieval": round(100 * n_no_retrieval / n_total, 1) if n_total else 0.0,
        "precision": round(sum(precs) / n, 4),
        "recall": round(sum(recs) / n, 4),
        "f1": round(sum(f1s) / n, 4),
        "hr": round(100 * sum(hr_vals) / n, 1),
        "err": round(100 * sum(1 for v in n_vals if v == 0) / n, 1),
    }
    for ns, vals in by_ns.items():
        nn = len(vals["f1s"])
        result[f"f1_{ns}"] = round(sum(vals["f1s"]) / nn, 4) if nn else 0.0
    return result


def main(args):
    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    print("Building reference set from RAG results...")
    ref_set = build_reference_set(results_dir)
    print(f"  |R| = {len(ref_set):,} unique GO terms seen in ground truth\n")

    rows = []
    for fp in sorted(results_dir.glob("*.jsonl")):
        raw_model = fp.stem
        # Try to recover the original model identifier for display lookup
        label = None
        for k, v in MODEL_DISPLAY.items():
            if k.replace("/", "_").replace(":", "-") == raw_model:
                label = v
                break
        label = label or raw_model

        metrics = evaluate_model(fp, ref_set)
        if metrics is None:
            print(f"  {label}: no successful records yet, skipping")
            continue
        metrics["model"] = label
        metrics["probe_p5_f1"] = PROBE_P5_F1.get(label)
        if metrics["probe_p5_f1"] is not None:
            metrics["delta_vs_p5"] = round(metrics["f1"] - metrics["probe_p5_f1"], 4)
        rows.append(metrics)

    rows.sort(key=lambda r: -r["f1"])

    print("=" * 100)
    print(f"{'Model':<20} {'N':>6} {'F1':>7} {'Prec':>7} {'Rec':>7} {'HR%':>6} "
          f"{'ERR%':>6} {'NoRetr%':>8} {'P5-F1':>7} {'Delta':>7}")
    print("-" * 100)
    for r in rows:
        p5 = f"{r['probe_p5_f1']:.3f}" if r["probe_p5_f1"] is not None else "  n/a"
        delta = f"{r['delta_vs_p5']:+.3f}" if r.get("delta_vs_p5") is not None else "  n/a"
        print(f"{r['model']:<20} {r['n']:>6} {r['f1']:>7.4f} {r['precision']:>7.4f} "
              f"{r['recall']:>7.4f} {r['hr']:>6.1f} {r['err']:>6.1f} "
              f"{r['pct_no_retrieval']:>7.1f}% {p5:>7} {delta:>7}")
    print("=" * 100)
    print("\nNote: results reflect whatever subset of proteins/models have been run so far")
    print("(e.g. a --limit pilot). N is the number of successful scored instances.")

    with open(output_dir / "rag_leaderboard.json", "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nSaved: {output_dir / 'rag_leaderboard.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results_dir", default="rag_results")
    parser.add_argument("--output_dir", default="rag_evaluation")
    args = parser.parse_args()
    main(args)
