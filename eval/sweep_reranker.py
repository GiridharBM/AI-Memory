"""Phase 3C threshold sweep for reranker abstention gate."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings
from app.infrastructure.search import SearchService
from app.infrastructure.reranker import CrossEncoderReranker, RerankerConfig
from app.application.qa_workflow import AbstentionGate


EVAL_DIR = Path(__file__).resolve().parent
DATASET_PATH = EVAL_DIR / "dataset.json"
RESULTS_DIR = EVAL_DIR / "results"


def load_dataset() -> dict:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def normalize_source(source: str) -> str:
    return source.split("\\")[-1].split("/")[-1]


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
    hit_name = normalize_source(hit_source).lower()
    for key in expected_sources:
        filename_part = SOURCE_KEY_TO_FILENAME.get(key, key).lower()
        if filename_part in hit_name or hit_name in filename_part:
            return True
    return False


def run_sweep():
    dataset = load_dataset()
    queries = dataset["queries"]

    settings = load_settings()
    search_service = SearchService.create_default(settings)

    # Load reranker
    cfg = RerankerConfig(enabled=True, top_n=20, device="cpu", timeout_seconds=10.0)
    reranker = CrossEncoderReranker(cfg)
    print("Loading reranker model...")
    reranker._ensure_loaded()
    if not reranker.is_loaded:
        print("ERROR: Reranker failed to load")
        return
    print("Reranker loaded.\n")

    # Pre-retrieve and rerank all queries
    print("Retrieving and reranking all queries...")
    query_data = []
    for q in queries:
        hits = search_service.search(q["query"], top_k=20)
        hits = reranker.rerank(q["query"], hits, top_k=10)
        hits = hits[:10]
        query_data.append({
            "id": q["id"],
            "query": q["query"],
            "expected_sources": q["expected_sources"],
            "hits": hits,
        })
    print(f"Done. {len(query_data)} queries processed.\n")

    # Threshold sweep
    thresholds = [0.0, 0.001, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]

    print(f"{'Threshold':>10} {'FPR':>6} {'FNR':>6} {'NegRej':>7} {'Hit@1':>6} {'Hit@5':>6} {'Recall@5':>8} {'MRR':>6} {'PosMRR':>7} {'AbstPos':>8} {'AbstNeg':>8}")
    print("-" * 110)

    for threshold in thresholds:
        gate = AbstentionGate(min_cosine=0.0, min_rerank_score=threshold)

        pos_queries = [q for q in query_data if q["expected_sources"]]
        neg_queries = [q for q in query_data if not q["expected_sources"]]

        abstained_pos = 0
        abstained_neg = 0
        hits_1 = 0
        hits_5 = 0
        recall_5_scores = []
        mrr_scores = []
        pos_mrr_scores = []

        for q in query_data:
            gate_result = gate.evaluate(q["hits"])
            abstained = gate_result.abstain

            if not q["expected_sources"]:
                if abstained:
                    abstained_neg += 1
                continue

            # Positive query
            if abstained:
                abstained_pos += 1
                continue

            # Check hit
            found_at = None
            for rank, hit in enumerate(q["hits"], 1):
                if match_source(hit.source, q["expected_sources"]):
                    found_at = rank
                    break

            if found_at is not None:
                if found_at <= 1:
                    hits_1 += 1
                if found_at <= 5:
                    hits_5 += 1
                mrr_scores.append(1.0 / found_at)
                pos_mrr_scores.append(1.0 / found_at)
            else:
                mrr_scores.append(0.0)
                pos_mrr_scores.append(0.0)

            # Recall@5
            sources_found = set()
            for hit in q["hits"][:5]:
                for exp in q["expected_sources"]:
                    if match_source(hit.source, [exp]):
                        sources_found.add(exp)
                        break
            recall_5_scores.append(len(sources_found) / len(q["expected_sources"]))

        n_pos = len(pos_queries)
        n_neg = len(neg_queries)
        fpr = (n_neg - abstained_neg) / n_neg if n_neg else 0
        fnr = abstained_pos / n_pos if n_pos else 0
        neg_rej = abstained_neg / n_neg if n_neg else 0
        hit1 = hits_1 / n_pos if n_pos else 0
        hit5 = hits_5 / n_pos if n_pos else 0
        recall5 = sum(recall_5_scores) / len(recall_5_scores) if recall_5_scores else 0
        mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0
        pos_mrr = sum(pos_mrr_scores) / len(pos_mrr_scores) if pos_mrr_scores else 0

        print(
            f"{threshold:>10.3f} {fpr:>6.3f} {fnr:>6.3f} {neg_rej:>7.3f} "
            f"{hit1:>6.3f} {hit5:>6.3f} {recall5:>8.3f} {mrr:>6.3f} {pos_mrr:>7.3f} "
            f"{abstained_pos:>8d} {abstained_neg:>8d}"
        )

    print("\nDone.")


if __name__ == "__main__":
    run_sweep()
