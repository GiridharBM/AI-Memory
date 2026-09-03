"""
Phase 3F — Reranker gate threshold sweep.

Runs the 160-query eval with:
  - reranker enabled
  - min_cosine=0.45 (frozen)
  - min_rerank_score = T (swept)

Thresholds: 0.05, 0.10, 0.12, 0.125, 0.15, 0.20

Records: Hit@1, Hit@5, MRR, FPR, FNR, abstention rate, latency.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.scripts.run_eval import run_evaluation


THRESHOLDS = [0.05, 0.10, 0.12, 0.125, 0.15, 0.20]
MIN_COSINE = 0.45

EXPERIMENT_2_MIN_COSINE = 0.01
EXPERIMENT_2_THRESHOLD = 0.125


def extract_gate_metrics(output: dict) -> dict:
    """Pull the metrics we care about from the eval output."""
    m = output.get("metrics", {})
    abstention = m.get("abstention", {})
    return {
        "hit@1": m.get("hit_rate@1", 0.0),
        "hit@5": m.get("hit_rate@5", 0.0),
        "mrr": m.get("mrr", 0.0),
        "mrr_pos": m.get("mrr_positive_only", 0.0),
        "fpr": abstention.get("false_positive_rate", 0.0),
        "fnr": abstention.get("false_negative_rate", 0.0),
        "abstention_rate": abstention.get("abstention_rate", 0.0),
        "positive_acceptance_rate": abstention.get("positive_acceptance_rate", 0.0),
        "negative_rejection_rate": abstention.get("negative_rejection_rate", 0.0),
        "avg_query_time_ms": m.get("avg_query_time_ms", 0.0),
    }


def run_sweep() -> list[dict]:
    """Experiment 1: Sweep reranker thresholds with min_cosine=0.45."""
    results = []
    for t in THRESHOLDS:
        print(f"\n{'='*70}")
        print(f"  THRESHOLD SWEEP: T = {t}")
        print(f"{'='*70}")
        output = run_evaluation(
            top_k=10,
            min_cosine=MIN_COSINE,
            reranker=True,
            min_rerank_score=t,
        )
        metrics = extract_gate_metrics(output)
        metrics["threshold"] = t
        results.append(metrics)
    return results


def run_experiment_2() -> dict:
    """Experiment 2: Reranker-only (min_cosine=0.0)."""
    print(f"\n{'='*70}")
    print(f"  EXPERIMENT 2: RERANKER-ONLY (min_cosine=0.0, T={EXPERIMENT_2_THRESHOLD})")
    print(f"{'='*70}")
    output = run_evaluation(
        top_k=10,
        min_cosine=EXPERIMENT_2_MIN_COSINE,
        reranker=True,
        min_rerank_score=EXPERIMENT_2_THRESHOLD,
    )
    metrics = extract_gate_metrics(output)
    metrics["experiment"] = "reranker_only"
    return metrics


def run_experiment_3(best_t: float) -> dict:
    """Experiment 3: Combined gate at optimal threshold."""
    print(f"\n{'='*70}")
    print(f"  EXPERIMENT 3: COMBINED GATE (min_cosine=0.45, T={best_t})")
    print(f"{'='*70}")
    output = run_evaluation(
        top_k=10,
        min_cosine=MIN_COSINE,
        reranker=True,
        min_rerank_score=best_t,
    )
    metrics = extract_gate_metrics(output)
    metrics["experiment"] = "combined_gate"
    metrics["threshold"] = best_t
    return metrics


def main() -> None:
    # ── Experiment 1: Threshold sweep ────────────────────────────────
    sweep_results = run_sweep()

    print(f"\n{'='*70}")
    print("  THRESHOLD SWEEP RESULTS")
    print(f"{'='*70}")
    header = f"{'T':>6} {'Hit@1':>6} {'Hit@5':>6} {'MRR':>6} {'FPR':>6} {'FNR':>6} {'Abstain':>8} {'+Acc':>6} {'-Rej':>6} {'QryTime':>8}"
    print(header)
    print("-" * len(header))
    for r in sweep_results:
        print(
            f"{r['threshold']:6.3f} {r['hit@1']:6.3f} {r['hit@5']:6.3f} "
            f"{r['mrr']:6.3f} {r['fpr']:6.3f} {r['fnr']:6.3f} "
            f"{r['abstention_rate']:8.3f} {r['positive_acceptance_rate']:6.3f} "
            f"{r['negative_rejection_rate']:6.3f} {r['avg_query_time_ms']:8.1f}"
        )

    # ── Select optimal threshold ─────────────────────────────────────
    # Constraints: FNR <= 0.033, Hit@5 >= 0.93, MRR >= 0.88
    candidates = [
        r for r in sweep_results
        if r["fnr"] <= 0.033 and r["hit@5"] >= 0.93 and r["mrr"] >= 0.88
    ]

    best_t = None
    if candidates:
        # Among valid candidates, prefer lowest FPR, then lowest latency
        candidates.sort(key=lambda r: (r["fpr"], r["avg_total_latency_ms"]))
        best_t = candidates[0]["threshold"]
        print(f"\nOptimal threshold: T = {best_t} (FPR={candidates[0]['fpr']:.3f}, FNR={candidates[0]['fnr']:.3f})")
    else:
        print("\nNO threshold satisfies constraints (FNR<=0.033, Hit@5>=0.93, MRR>=0.88)")

    # ── Experiment 2: Reranker-only ──────────────────────────────────
    exp2 = run_experiment_2()

    print(f"\n{'='*70}")
    print("  EXPERIMENT 2 RESULTS: RERANKER-ONLY")
    print(f"{'='*70}")
    print(f"  min_cosine=0.0, min_rerank_score={EXPERIMENT_2_THRESHOLD}")
    print(f"  Hit@1={exp2['hit@1']:.3f}, Hit@5={exp2['hit@5']:.3f}, MRR={exp2['mrr']:.3f}")
    print(f"  FPR={exp2['fpr']:.3f}, FNR={exp2['fnr']:.3f}")
    print(f"  Abstention rate={exp2['abstention_rate']:.3f}")
    print(f"  Avg query time={exp2['avg_query_time_ms']:.1f}ms")

    # ── Experiment 3: Combined gate ──────────────────────────────────
    if best_t is not None:
        exp3 = run_experiment_3(best_t)

        print(f"\n{'='*70}")
        print("  EXPERIMENT 3 RESULTS: COMBINED GATE")
        print(f"{'='*70}")
        print(f"  min_cosine=0.45, min_rerank_score={best_t}")
        print(f"  Hit@1={exp3['hit@1']:.3f}, Hit@5={exp3['hit@5']:.3f}, MRR={exp3['mrr']:.3f}")
        print(f"  FPR={exp3['fpr']:.3f}, FNR={exp3['fnr']:.3f}")
        print(f"  Abstention rate={exp3['abstention_rate']:.3f}")
        print(f"  Avg query time={exp3['avg_query_time_ms']:.1f}ms")
    else:
        exp3 = None
        print("\nSkipping Experiment 3: no valid threshold found")

    # ── Save all results ─────────────────────────────────────────────
    all_results = {
        "experiment_1_sweep": sweep_results,
        "experiment_2_reranker_only": exp2,
        "experiment_3_combined": exp3,
        "selected_threshold": best_t,
    }
    out_path = Path(__file__).resolve().parent / "results" / "phase_3f_sweep.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
