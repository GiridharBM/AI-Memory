"""Threshold sweep for the abstention gate.

Runs the retrieval evaluation at multiple min_cosine thresholds and produces
a comparison table.  Uses the SAME search infrastructure and dataset as
run_eval.py — no code modifications.

Usage:
    python eval/scripts/sweep_thresholds.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.application.qa_workflow import AbstentionGate  # noqa: E402
from app.core.config import load_settings  # noqa: E402
from app.infrastructure.search import SearchService  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = EVAL_DIR / "datasets" / "dataset.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Same source mapping as run_eval.py
SOURCE_KEY_TO_FILENAME = {
    "neural_networks": "But what is a neural network",
    "daa_assignment": "DAA assignment-4",
    "jharkhand_protest": "Jharkhand job exam stir",
    "gpt56_demo": "Meet _GPT-5.6",
    "openhands": "OpenHands",
    "utthunga": "Our Organization",
    "pcb_design": "PCB Board Design",
    "leetcode": "What I Learned From LeetCode",
    "tihan": "WhatsApp Image",
    "b_md": "b.md",
    "pam_smoke_test": "pam_smoke_test",
    "sigmamusicart": "sigmamusicart",
}


def normalize_source(source: str) -> str:
    return source.split("\\")[-1].split("/")[-1]


def match_source(hit_source: str, expected_sources: list[str]) -> bool:
    hit_name = normalize_source(hit_source).lower()
    for key in expected_sources:
        filename_part = SOURCE_KEY_TO_FILENAME.get(key, key).lower()
        if filename_part in hit_name or hit_name in filename_part:
            return True
    return False


def evaluate_at_threshold(
    queries: list[dict],
    search_service: SearchService,
    threshold: float,
    top_k: int = 10,
) -> dict:
    gate = AbstentionGate(min_cosine=threshold)
    total_time = 0.0

    pos_accepted = 0
    pos_total = 0
    neg_rejected = 0
    neg_total = 0
    abstained_total = 0
    mrr_sum = 0.0
    mrr_count = 0
    hit_at_1 = 0
    hit_at_5 = 0
    recall_at_5_sum = 0.0
    recall_at_10_sum = 0.0
    pos_count_for_recall = 0

    per_query = []

    for q in queries:
        is_positive = bool(q["expected_sources"])
        if is_positive:
            pos_total += 1
        else:
            neg_total += 1

        q_start = time.time()
        hits = search_service.search(q["query"], top_k=top_k)
        q_time = time.time() - q_start
        total_time += q_time

        abstention = gate.evaluate(hits)
        abstained = abstention.abstain

        if abstained:
            abstained_total += 1
            if is_positive:
                pass  # FNR case
            else:
                neg_rejected += 1
        else:
            if is_positive:
                pos_accepted += 1
                # Compute rank of first matching source
                found_at_rank = None
                for rank, h in enumerate(hits, 1):
                    if match_source(h.source, q["expected_sources"]):
                        found_at_rank = rank
                        break
                if found_at_rank is not None:
                    mrr_sum += 1.0 / found_at_rank
                    if found_at_rank <= 1:
                        hit_at_1 += 1
                    if found_at_rank <= 5:
                        hit_at_5 += 1
                mrr_count += 1

                # Recall computation
                retrieved_sources = [h.source for h in hits[:10]]
                sources_found = set()
                for s in retrieved_sources:
                    for exp in q["expected_sources"]:
                        if match_source(s, [exp]):
                            sources_found.add(exp)
                            break
                recall_at_5_sum += len(sources_found) / len(q["expected_sources"]) if q["expected_sources"] else 0
                sources_found_10 = set()
                for s in retrieved_sources[:10]:
                    for exp in q["expected_sources"]:
                        if match_source(s, [exp]):
                            sources_found_10.add(exp)
                            break
                recall_at_10_sum += len(sources_found_10) / len(q["expected_sources"]) if q["expected_sources"] else 0
                pos_count_for_recall += 1

        per_query.append({
            "id": q["id"],
            "abstained": abstained,
            "is_positive": is_positive,
            "cosine": hits[0].cosine_score if hits else 0.0,
        })

    fpr = 1.0 - (neg_rejected / neg_total) if neg_total else 0.0
    fnr = 1.0 - (pos_accepted / pos_total) if pos_total else 0.0
    hit_rate_1 = hit_at_1 / pos_count_for_recall if pos_count_for_recall else 0
    hit_rate_5 = hit_at_5 / pos_count_for_recall if pos_count_for_recall else 0
    recall_5 = recall_at_5_sum / pos_count_for_recall if pos_count_for_recall else 0
    recall_10 = recall_at_10_sum / pos_count_for_recall if pos_count_for_recall else 0
    mrr = mrr_sum / mrr_count if mrr_count else 0
    abstention_rate = abstained_total / len(queries) if queries else 0
    pos_acceptance = pos_accepted / pos_total if pos_total else 0
    neg_rejection_rate = neg_rejected / neg_total if neg_total else 0

    return {
        "threshold": round(threshold, 4),
        "hit_rate@1": round(hit_rate_1, 4),
        "hit_rate@5": round(hit_rate_5, 4),
        "recall@5": round(recall_5, 4),
        "recall@10": round(recall_10, 4),
        "mrr": round(mrr, 4),
        "fpr": round(fpr, 4),
        "fnr": round(fnr, 4),
        "abstention_rate": round(abstention_rate, 4),
        "pos_acceptance": round(pos_acceptance, 4),
        "neg_rejection": round(neg_rejection_rate, 4),
        "abstained_count": abstained_total,
        "pos_rejected_count": pos_total - pos_accepted,
        "neg_rejected_count": neg_rejected,
        "avg_latency_ms": round(total_time / len(queries) * 1000, 1) if queries else 0,
    }


def main() -> None:
    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)
    queries = dataset["queries"]

    settings = load_settings()
    search_service = SearchService.create_default(settings)

    # Collect raw cosine scores for all queries (baseline, no gate)
    print("Collecting baseline cosine scores...")
    cosine_scores = []
    for q in queries:
        hits = search_service.search(q["query"], top_k=10)
        cos = hits[0].cosine_score if hits else 0.0
        cosine_scores.append({
            "id": q["id"],
            "query": q["query"][:60],
            "is_positive": bool(q["expected_sources"]),
            "cosine": round(cos, 6),
        })

    # Sort by cosine for distribution analysis
    cosine_scores.sort(key=lambda x: x["cosine"])

    print("\nCosine score distribution (sorted low to high):")
    print(f"{'ID':<6} {'Cosine':>8} {'Type':<9} Query")
    print("-" * 80)
    for cs in cosine_scores:
        marker = "+" if cs["is_positive"] else "~"
        print(f"  {marker} {cs['id']:<5} {cs['cosine']:>8.4f}  {cs['query']}")

    # Determine threshold range from actual distribution
    pos_scores = [cs["cosine"] for cs in cosine_scores if cs["is_positive"]]
    neg_scores = [cs["cosine"] for cs in cosine_scores if not cs["is_positive"]]
    min_pos = min(pos_scores) if pos_scores else 0
    max_neg = max(neg_scores) if neg_scores else 0

    print(f"\nPositive range: [{min_pos:.4f}, {max(pos_scores):.4f}]")
    print(f"Negative range: [{min(neg_scores):.4f}, {max_neg:.4f}]")
    print(f"Overlap zone: [{min_pos:.4f}, {max_neg:.4f}]")

    # Generate thresholds: cover the full range with fine granularity in the overlap zone
    thresholds = [0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    # Add thresholds at each unique cosine value in the overlap zone (4 decimal places)
    overlap_scores = sorted(set(
        round(cs["cosine"], 4)
        for cs in cosine_scores
        if min_pos - 0.05 <= cs["cosine"] <= max_neg + 0.05
    ))
    for s in overlap_scores:
        if s not in thresholds:
            thresholds.append(s)
    thresholds = sorted(set(thresholds))

    print(f"\nEvaluating {len(thresholds)} thresholds...")

    # Run sweep
    results = []
    for t in thresholds:
        r = evaluate_at_threshold(queries, search_service, t)
        results.append(r)

    # Print comparison table with full precision
    print("\n" + "=" * 130)
    print("THRESHOLD COMPARISON TABLE")
    print("=" * 130)
    header = (
        f"{'Threshold':>10} | {'Hit@1':>6} | {'Hit@5':>6} | {'Rec@5':>6} | {'Rec@10':>6} | "
        f"{'MRR':>6} | {'FPR':>6} | {'FNR':>6} | {'AbstRate':>8} | {'PosAcc':>6} | {'NegRej':>6} | {'PosLost':>7}"
    )
    print(header)
    print("-" * 130)
    for r in results:
        print(
            f"  {r['threshold']:>8.4f} | {r['hit_rate@1']:>6.3f} | {r['hit_rate@5']:>6.3f} | "
            f"{r['recall@5']:>6.3f} | {r['recall@10']:>6.3f} | {r['mrr']:>6.3f} | "
            f"{r['fpr']:>6.3f} | {r['fnr']:>6.3f} | {r['abstention_rate']:>8.3f} | "
            f"{r['pos_acceptance']:>6.3f} | {r['neg_rejection']:>6.3f} | {r['pos_rejected_count']:>7d}"
        )

    # Save results
    output = {
        "metadata": {
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "dataset": str(DATASET_PATH),
            "thresholds_evaluated": thresholds,
        },
        "cosine_distribution": cosine_scores,
        "sweep_results": results,
    }
    result_path = RESULTS_DIR / "threshold_sweep.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed results saved to: {result_path}")


if __name__ == "__main__":
    main()
