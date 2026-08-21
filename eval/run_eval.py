"""
PAM V1 Retrieval Evaluation — Baseline + Abstention Measurement.

Measures Hit Rate, Recall@K, Precision@K, MRR, and abstention metrics
(FPR, FNR, abstention rate) against a ground-truth dataset of 50 queries
against 12 documents in the existing vector store.

NO source code is modified. Uses PAM's existing search infrastructure as-is.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# ── Load PAM infrastructure (no modifications) ──────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings  # noqa: E402
from app.infrastructure.search import SearchService  # noqa: E402

# Abstention gate (imported for per-query evaluation)
from app.application.qa_workflow import AbstentionGate  # noqa: E402

# Reranker (optional)
from app.infrastructure.reranker import CrossEncoderReranker, RerankerConfig  # noqa: E402


# ── Paths ───────────────────────────────────────────────────────────────
EVAL_DIR = Path(__file__).resolve().parent
DATASET_PATH = EVAL_DIR / "dataset.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def load_dataset() -> dict:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def normalize_source(source: str) -> str:
    """Extract filename from full path for matching."""
    return source.split("\\")[-1].split("/")[-1]


# Map short keys to actual filenames in the vector store
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


def match_source(hit_source: str, expected_sources: list[str]) -> bool:
    """Check if a search hit source matches any expected source."""
    hit_name = normalize_source(hit_source).lower()
    for key in expected_sources:
        filename_part = SOURCE_KEY_TO_FILENAME.get(key, key).lower()
        if filename_part in hit_name or hit_name in filename_part:
            return True
    return False


def compute_metrics(
    results: list[dict],
    ks: list[int] | None = None,
) -> dict:
    """Compute retrieval metrics across all queries."""
    if ks is None:
        ks = [1, 3, 5, 10]

    total = len(results)
    if total == 0:
        return {"error": "no results"}

    # Per-query metrics (only for queries WITH ground truth)
    positive_results = [r for r in results if r["expected_sources"]]
    negative_results = [r for r in results if not r["expected_sources"]]

    hit_rates = {k: 0 for k in ks}
    recalls = {k: [] for k in ks}
    precisions = {k: [] for k in ks}
    mrr_scores = []

    for r in results:
        expected = r["expected_sources"]
        retrieved_sources = [hit["source"] for hit in r["hits"]]

        if not expected:
            # Negative query: check if system returns results (it always does for semantic search)
            # A perfect system would return nothing or low-score results
            mrr_scores.append(1.0)  # Negative queries are always "correct" for MRR (no expected source to miss)
            continue

        # Check if any expected source appears in top-K
        found_at_rank = None
        for rank, src in enumerate(retrieved_sources, 1):
            if match_source(src, expected):
                found_at_rank = rank
                break

        # Hit Rate@K
        for k in ks:
            if found_at_rank is not None and found_at_rank <= k:
                hit_rates[k] += 1

        # MRR
        mrr_scores.append(1.0 / found_at_rank if found_at_rank else 0.0)

        # Recall@K and Precision@K (only for positive queries)
        for k in ks:
            top_k_sources = retrieved_sources[:k]
            # Count distinct expected sources found in top-K
            sources_found = set()
            for s in top_k_sources:
                for exp in expected:
                    if match_source(s, [exp]):
                        sources_found.add(exp)
                        break
            relevant_in_top_k = len(sources_found)
            recalls[k].append(relevant_in_top_k / len(expected) if expected else 0.0)
            precisions[k].append(relevant_in_top_k / k if k > 0 else 0.0)

    # Aggregate (Recall/Precision only over positive queries)
    n_pos = len(positive_results)
    n_neg = len(negative_results)
    metrics = {
        "total_queries": total,
        "queries_with_ground_truth": n_pos,
        "negative_queries": n_neg,
    }

    for k in ks:
        metrics[f"hit_rate@{k}"] = hit_rates[k] / n_pos if n_pos else 0
        metrics[f"recall@{k}"] = (
            sum(recalls[k]) / len(recalls[k]) if recalls[k] else 0
        )
        metrics[f"precision@{k}"] = (
            sum(precisions[k]) / len(precisions[k]) if precisions[k] else 0
        )

    metrics["mrr"] = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0

    # Per-category breakdown
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "hits_5": 0, "mrr": []}
        categories[cat]["count"] += 1
        found = False
        for rank, hit in enumerate(r["hits"][:5], 1):
            if match_source(hit["source"], r["expected_sources"]):
                found = True
                categories[cat]["mrr"].append(1.0 / rank)
                break
        if found:
            categories[cat]["hits_5"] += 1
        elif not r["expected_sources"]:
            categories[cat]["mrr"].append(1.0)  # Correct negative

    metrics["per_category"] = {}
    for cat, data in categories.items():
        metrics["per_category"][cat] = {
            "count": data["count"],
            "hit_rate@5": data["hits_5"] / data["count"] if data["count"] else 0,
            "mrr": (
                sum(data["mrr"]) / len(data["mrr"]) if data["mrr"] else 0
            ),
        }

    return metrics


def run_evaluation(
    top_k: int = 10,
    min_cosine: float = 0.25,
    reranker: bool = False,
    reranker_model: str | None = None,
    min_rerank_score: float = 0.0,
) -> dict:
    """Run full evaluation against the dataset.

    Parameters
    ----------
    top_k:
        Number of results to retrieve per query.
    min_cosine:
        Cosine threshold for the abstention gate.  Set to ``0.0`` to disable
        gating and collect raw scores only (baseline mode).
    reranker:
        Enable cross-encoder reranking.
    reranker_model:
        Model name for the reranker.  Defaults to
        ``cross-encoder/ms-marco-MiniLM-L-12-v2``.
    min_rerank_score:
        Threshold for the reranker abstention gate.  0.0 = no reranker gating.
    """
    gate_enabled = min_cosine > 0.0
    gate = AbstentionGate(min_cosine=min_cosine) if gate_enabled else None

    # Reranker setup
    reranker_cfg: CrossEncoderReranker | None = None
    if reranker:
        cfg = RerankerConfig(
            enabled=True,
            model=reranker_model or "cross-encoder/ms-marco-MiniLM-L-12-v2",
            top_n=20,
            device="cpu",
            timeout_seconds=10.0,
        )
        reranker_cfg = CrossEncoderReranker(cfg)
        # Update gate with reranker threshold
        if gate is not None:
            gate = AbstentionGate(min_cosine=min_cosine, min_rerank_score=min_rerank_score)
        elif min_rerank_score > 0.0:
            gate = AbstentionGate(min_cosine=0.0, min_rerank_score=min_rerank_score)

    mode_str = " — BASELINE"
    if gate_enabled:
        mode_str = " — ABSTENTION GATE"
    if reranker_cfg:
        mode_str += " + RERANKER"

    print("=" * 70)
    print("PAM V1 Retrieval Evaluation" + mode_str)
    print("=" * 70)

    # Load dataset
    dataset = load_dataset()
    queries = dataset["queries"]
    print(f"\nDataset: {len(queries)} queries")
    print(f"Categories: {set(q['category'] for q in queries)}")

    # Initialize PAM search (unmodified)
    print("\nInitializing PAM search infrastructure...")
    settings = load_settings()
    search_service = SearchService.create_default(settings)

    # Check vector store
    store = search_service._store
    all_entries = store.entries()
    print(f"Vector store entries: {len(all_entries)}")
    if not all_entries:
        print("\nWARNING: Vector store is empty. No documents have been ingested.")
        print("The evaluation will measure baseline behavior with an empty store.")
        print("Ingest documents first, then re-run this evaluation.")

    # Embedding check
    print("\nChecking embedding service...")
    try:
        test_emb = search_service._embed("test")
        if test_emb is not None:
            print(f"Embedding service: OK (dimension={len(test_emb)})")
        else:
            print("Embedding service: FAILED (degraded to BM25-only)")
    except Exception as e:
        print(f"Embedding service: ERROR ({e}) — degraded to BM25-only")

    # Run queries
    print(f"\nRunning {len(queries)} queries (top_k={top_k})...")
    results = []
    rerank_latencies = []
    retrieval_latencies = []
    start_time = time.time()

    for i, q in enumerate(queries, 1):
        q_start = time.time()

        # Retrieve extra candidates if reranker is active
        search_top_k = max(top_k, 20) if reranker_cfg else top_k
        hits = search_service.search(q["query"], top_k=search_top_k)
        retrieval_time = time.time() - q_start
        retrieval_latencies.append(retrieval_time * 1000)

        # Rerank if enabled
        r_start = time.time()
        if reranker_cfg and hits:
            hits = reranker_cfg.rerank(q["query"], hits, top_k=top_k)
        hits = hits[:top_k]
        rerank_time = time.time() - r_start
        if reranker_cfg:
            rerank_latencies.append(rerank_time * 1000)

        q_time = time.time() - q_start

        hit_list = [
            {
                "source": normalize_source(h.source),
                "full_source": h.source,
                "score": round(h.score, 6),
                "cosine_score": round(h.cosine_score, 6),
                "bm25_score": round(h.bm25_score, 6),
                "rerank_score": round(h.rerank_score, 6),
                "text_preview": h.text[:100].replace("\n", " "),
            }
            for h in hits
        ]

        # Check ground truth match
        matched = False
        matched_source = None
        for rank, h in enumerate(hits, 1):
            if match_source(h.source, q["expected_sources"]):
                matched = True
                matched_source = normalize_source(h.source)
                break

        # Abstention gate evaluation
        abstained = False
        abstention_reason = None
        if gate is not None:
            result = gate.evaluate(hits)
            abstained = result.abstain
            abstention_reason = result.reason

        status = "HIT" if matched else ("NEG" if not q["expected_sources"] else "MISS")
        if abstained:
            status = "ABSTAIN"
        marker = {"HIT": "+", "NEG": "~", "MISS": "x", "ABSTAIN": "A"}[status]

        result = {
            "id": q["id"],
            "query": q["query"],
            "category": q["category"],
            "difficulty": q["difficulty"],
            "expected_sources": q["expected_sources"],
            "hits": hit_list,
            "matched": matched,
            "matched_source": matched_source,
            "query_time_ms": round(q_time * 1000, 1),
            "ground_truth_reliable": q.get("ground_truth_reliable", True),
            "notes": q.get("notes", ""),
            "abstained": abstained,
            "abstention_reason": abstention_reason,
        }
        results.append(result)

        top_source = hit_list[0]["source"] if hit_list else "none"
        top_cosine = hit_list[0]["cosine_score"] if hit_list else 0
        gate_str = f" | gate={abstention_reason}" if abstained else ""
        print(
            f"  [{marker}] {q['id']} ({q_time*1000:.0f}ms) "
            f"top={top_source} cos={top_cosine:.4f}{gate_str} | {q['query'][:50]}"
        )

    total_time = time.time() - start_time

    # Compute metrics
    print("\nComputing metrics...")
    metrics = compute_metrics(results)
    metrics["total_time_seconds"] = round(total_time, 2)
    metrics["avg_query_time_ms"] = round(total_time / len(queries) * 1000, 1)
    metrics["top_k"] = top_k

    # Latency breakdown
    if retrieval_latencies:
        metrics["avg_retrieval_latency_ms"] = round(
            sum(retrieval_latencies) / len(retrieval_latencies), 1
        )
    if rerank_latencies:
        metrics["avg_rerank_latency_ms"] = round(
            sum(rerank_latencies) / len(rerank_latencies), 1
        )
        metrics["reranker_enabled"] = True
    else:
        metrics["reranker_enabled"] = False

    # Abstention metrics
    positive_results = [r for r in results if r["expected_sources"]]
    negative_results = [r for r in results if not r["expected_sources"]]
    n_pos = len(positive_results)
    n_neg = len(negative_results)

    abstained_pos = sum(1 for r in positive_results if r["abstained"])
    abstained_neg = sum(1 for r in negative_results if r["abstained"])
    abstained_total = abstained_pos + abstained_neg

    metrics["abstention"] = {
        "gate_enabled": gate_enabled,
        "min_cosine": min_cosine,
        "false_positive_rate": (n_neg - abstained_neg) / n_neg if n_neg else 0,
        "false_negative_rate": abstained_pos / n_pos if n_pos else 0,
        "abstention_rate": abstained_total / len(results) if results else 0,
        "positive_acceptance_rate": 1 - (abstained_pos / n_pos) if n_pos else 1,
        "negative_rejection_rate": abstained_neg / n_neg if n_neg else 0,
        "abstained_positive_count": abstained_pos,
        "abstained_negative_count": abstained_neg,
    }

    # Recompute positive-only MRR (excluding abstained positives)
    if gate_enabled and positive_results:
        pos_mrr_scores = []
        for r in positive_results:
            if r["abstained"]:
                continue
            found_at_rank = None
            for rank, src in enumerate([hit["source"] for hit in r["hits"]], 1):
                if match_source(src, r["expected_sources"]):
                    found_at_rank = rank
                    break
            pos_mrr_scores.append(1.0 / found_at_rank if found_at_rank else 0.0)
        metrics["mrr_positive_only"] = (
            sum(pos_mrr_scores) / len(pos_mrr_scores) if pos_mrr_scores else 0
        )

    # Print summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total queries:      {metrics['total_queries']}")
    print(f"With ground truth:  {metrics['queries_with_ground_truth']}")
    print(f"Negative queries:   {metrics['negative_queries']}")
    print(f"Total time:         {metrics['total_time_seconds']}s")
    print(f"Avg query time:     {metrics['avg_query_time_ms']}ms")
    if metrics.get("reranker_enabled"):
        print(f"Avg retrieval:      {metrics.get('avg_retrieval_latency_ms', 'N/A')}ms")
        print(f"Avg reranking:      {metrics.get('avg_rerank_latency_ms', 'N/A')}ms")
        print(f"Reranker model:     {reranker_cfg.model_name if reranker_cfg else 'N/A'}")
    print()
    for k in [1, 3, 5, 10]:
        print(
            f"  Hit Rate@{k}:  {metrics[f'hit_rate@{k}']:.3f}  |  "
            f"Recall@{k}:  {metrics[f'recall@{k}']:.3f}  |  "
            f"Precision@{k}: {metrics[f'precision@{k}']:.3f}"
        )
    print(f"  MRR:             {metrics['mrr']:.3f}")

    abst = metrics.get("abstention", {})
    if abst.get("gate_enabled"):
        print(f"\n  Abstention Gate (min_cosine={abst['min_cosine']}):")
        print(f"    FPR:                {abst['false_positive_rate']:.3f}")
        print(f"    FNR:                {abst['false_negative_rate']:.3f}")
        print(f"    Abstention rate:    {abst['abstention_rate']:.3f}")
        print(f"    Pos acceptance:     {abst['positive_acceptance_rate']:.3f}")
        print(f"    Neg rejection:      {abst['negative_rejection_rate']:.3f}")
        if "mrr_positive_only" in metrics:
            print(f"    MRR (pos-only):     {metrics['mrr_positive_only']:.3f}")
    else:
        print("\n  Abstention gate: DISABLED (baseline mode)")
        print("    (Raw cosine/bm25 scores collected for threshold calibration)")

    print("\nPer-category breakdown:")
    for cat, data in metrics.get("per_category", {}).items():
        print(
            f"  {cat:20s}  count={data['count']:2d}  "
            f"hit@5={data['hit_rate@5']:.3f}  mrr={data['mrr']:.3f}"
        )

    # Identify unreliable ground truth
    unreliable = [r for r in results if not r["ground_truth_reliable"]]
    if unreliable:
        print(f"\nQueries with UNRELIABLE ground truth ({len(unreliable)}):")
        for r in unreliable:
            print(f"  {r['id']}: {r['query']}")
            if r["notes"]:
                print(f"    Note: {r['notes']}")

    # Save results
    output = {
        "metadata": {
            "evaluation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "dataset_version": dataset["metadata"]["version"],
            "total_documents_in_store": len(all_entries),
            "vector_store_path": str(
                settings.paths.manifest_root / "vector_store.json"
            ),
            "top_k": top_k,
            "gate_enabled": gate_enabled,
            "min_cosine": min_cosine,
            "reranker_enabled": reranker_cfg is not None,
            "reranker_model": reranker_cfg.model_name if reranker_cfg else None,
            "min_rerank_score": min_rerank_score,
            "source_code_modified": False,
            "notes": (
                f"{'ABSTENTION GATE' if gate_enabled else 'BASELINE'} evaluation"
                f" — min_cosine={min_cosine}"
                f"{' + RERANKER' if reranker_cfg else ''}"
            ),
        },
        "metrics": metrics,
        "queries": results,
    }

    # Save detailed results
    if reranker_cfg:
        result_filename = "reranker_eval.json"
    elif gate_enabled:
        result_filename = "abstention_gate.json"
    else:
        result_filename = "baseline_v1.json"
    result_path = RESULTS_DIR / result_filename
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed results saved to: {result_path}")

    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PAM V1 Retrieval Evaluation")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results per query")
    parser.add_argument(
        "--min-cosine",
        type=float,
        default=0.0,
        help="Cosine threshold for abstention gate (0.0 = baseline mode, no gate)",
    )
    parser.add_argument(
        "--reranker",
        action="store_true",
        help="Enable cross-encoder reranking",
    )
    parser.add_argument(
        "--reranker-model",
        type=str,
        default=None,
        help="Cross-encoder model name (default: cross-encoder/ms-marco-MiniLM-L-12-v2)",
    )
    parser.add_argument(
        "--min-rerank-score",
        type=float,
        default=0.0,
        help="Reranker abstention threshold (0.0 = no reranker gating)",
    )
    args = parser.parse_args()
    run_evaluation(
        top_k=args.top_k,
        min_cosine=args.min_cosine,
        reranker=args.reranker,
        reranker_model=args.reranker_model,
        min_rerank_score=args.min_rerank_score,
    )
