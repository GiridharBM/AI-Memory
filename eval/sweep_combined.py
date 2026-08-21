"""Phase 3C combined threshold sweep: reranker + cosine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings
from app.infrastructure.search import SearchService
from app.infrastructure.reranker import CrossEncoderReranker, RerankerConfig
from app.application.qa_workflow import AbstentionGate


EVAL_DIR = Path(__file__).resolve().parent
DATASET_PATH = EVAL_DIR / "dataset.json"


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

    cfg = RerankerConfig(enabled=True, top_n=20, device="cpu", timeout_seconds=10.0)
    reranker = CrossEncoderReranker(cfg)
    print("Loading reranker model...")
    reranker._ensure_loaded()
    if not reranker.is_loaded:
        print("ERROR: Reranker failed to load")
        return
    print("Reranker loaded.\n")

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

    # Combined threshold sweep
    combos = [
        # (min_cosine, min_rerank_score, label)
        (0.45, 0.00, "Phase 3B only (cosine=0.45)"),
        (0.00, 0.05, "Reranker only (rerank=0.05)"),
        (0.45, 0.01, "cosine=0.45 + rerank=0.01"),
        (0.45, 0.05, "cosine=0.45 + rerank=0.05"),
        (0.45, 0.10, "cosine=0.45 + rerank=0.10"),
        (0.45, 0.15, "cosine=0.45 + rerank=0.15"),
        (0.35, 0.05, "cosine=0.35 + rerank=0.05"),
        (0.35, 0.10, "cosine=0.35 + rerank=0.10"),
        (0.30, 0.05, "cosine=0.30 + rerank=0.05"),
        (0.00, 0.00, "No gate (raw reranking only)"),
    ]

    print(f"{'Config':<35} {'FPR':>6} {'FNR':>6} {'NegRej':>7} {'Hit@1':>6} {'Hit@5':>6} {'MRR':>6} {'PosMRR':>7}")
    print("-" * 100)

    for min_cos, min_rerank, label in combos:
        gate = AbstentionGate(min_cosine=min_cos, min_rerank_score=min_rerank)

        pos_queries = [q for q in query_data if q["expected_sources"]]
        neg_queries = [q for q in query_data if not q["expected_sources"]]

        abstained_pos = 0
        abstained_neg = 0
        hits_1 = 0
        hits_5 = 0
        mrr_scores = []
        pos_mrr_scores = []

        for q in query_data:
            gate_result = gate.evaluate(q["hits"])
            abstained = gate_result.abstain

            if not q["expected_sources"]:
                if abstained:
                    abstained_neg += 1
                continue

            if abstained:
                abstained_pos += 1
                continue

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

        n_pos = len(pos_queries)
        n_neg = len(neg_queries)
        fpr = (n_neg - abstained_neg) / n_neg if n_neg else 0
        fnr = abstained_pos / n_pos if n_pos else 0
        neg_rej = abstained_neg / n_neg if n_neg else 0
        hit1 = hits_1 / n_pos if n_pos else 0
        hit5 = hits_5 / n_pos if n_pos else 0
        mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0
        pos_mrr = sum(pos_mrr_scores) / len(pos_mrr_scores) if pos_mrr_scores else 0

        print(
            f"{label:<35} {fpr:>6.3f} {fnr:>6.3f} {neg_rej:>7.3f} "
            f"{hit1:>6.3f} {hit5:>6.3f} {mrr:>6.3f} {pos_mrr:>7.3f}"
        )

    print("\nDone.")


if __name__ == "__main__":
    run_sweep()
