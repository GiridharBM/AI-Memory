"""Backward compatibility check: run evaluation against the frozen v1 (50-query) dataset.

Verifies that retrieval results on the original 50 queries are unchanged
after the Phase 3D MRR bug fix.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings
from app.infrastructure.search import SearchService
from app.application.qa_workflow import AbstentionGate

EVAL_DIR = Path(__file__).resolve().parent
FROZEN_DATASET = EVAL_DIR / "dataset_v1_frozen.json"

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


def main():
    with open(FROZEN_DATASET, encoding="utf-8") as f:
        ds = json.load(f)
    queries = ds["queries"]

    print(f"Frozen v1 dataset: {len(queries)} queries")

    settings = load_settings()
    search_service = SearchService.create_default(settings)
    gate = AbstentionGate(min_cosine=0.45)

    results = []
    for q in queries:
        hits = search_service.search(q["query"], top_k=10)
        expected = q["expected_sources"]

        # Check match
        matched = False
        found_at_rank = None
        for rank, h in enumerate(hits, 1):
            if match_source(h.source, expected):
                matched = True
                found_at_rank = rank
                break

        # Gate check
        result = gate.evaluate(hits)
        abstained = result.abstain

        results.append({
            "id": q["id"],
            "expected_sources": expected,
            "matched": matched,
            "found_at_rank": found_at_rank,
            "abstained": abstained,
            "category": q["category"],
        })

    # Compute metrics
    pos_results = [r for r in results if r["expected_sources"]]
    neg_results = [r for r in results if not r["expected_sources"]]
    n_pos = len(pos_results)
    n_neg = len(neg_results)

    hit1 = sum(1 for r in pos_results if r["found_at_rank"] and r["found_at_rank"] <= 1) / n_pos
    hit5 = sum(1 for r in pos_results if r["found_at_rank"] and r["found_at_rank"] <= 5) / n_pos
    mrr_pos = sum(1.0/r["found_at_rank"] for r in pos_results if r["found_at_rank"]) / n_pos

    abstained_pos = sum(1 for r in pos_results if r["abstained"])
    abstained_neg = sum(1 for r in neg_results if r["abstained"])
    fpr = (n_neg - abstained_neg) / n_neg if n_neg else 0
    fnr = abstained_pos / n_pos if n_pos else 0
    neg_rejection = abstained_neg / n_neg if n_neg else 0

    print(f"\nFrozen v1 Results (min_cosine=0.45):")
    print(f"  Hit@1:  {hit1:.3f}")
    print(f"  Hit@5:  {hit5:.3f}")
    print(f"  MRR (pos-only): {mrr_pos:.3f}")
    print(f"  FPR:    {fpr:.3f}")
    print(f"  FNR:    {fnr:.3f}")
    print(f"  Neg rejection:  {neg_rejection:.3f}")

    # Compare against Phase 3B reported baseline
    expected_hit1 = 0.907
    expected_hit5 = 0.953
    expected_mrr_pos_only = 0.930  # corrected positive-only MRR
    expected_fpr = 0.714

    print(f"\nPhase 3B Baseline Comparison:")
    print(f"  Hit@1:   reported={expected_hit1:.3f}  current={hit1:.3f}  {'PASS' if abs(hit1 - expected_hit1) < 0.001 else 'DIFF'}")
    print(f"  Hit@5:   reported={expected_hit5:.3f}  current={hit5:.3f}  {'PASS' if abs(hit5 - expected_hit5) < 0.001 else 'DIFF'}")
    print(f"  MRR:     reported={expected_mrr_pos_only:.3f} (pos-only)  current={mrr_pos:.3f}  {'PASS' if abs(mrr_pos - expected_mrr_pos_only) < 0.001 else 'DIFF'}")
    print(f"  FPR:     reported={expected_fpr:.3f}  current={fpr:.3f}  {'PASS' if abs(fpr - expected_fpr) < 0.001 else 'DIFF'}")

    all_pass = (
        abs(hit1 - expected_hit1) < 0.001
        and abs(hit5 - expected_hit5) < 0.001
        and abs(mrr_pos - expected_mrr_pos_only) < 0.001
        and abs(fpr - expected_fpr) < 0.001
    )
    print(f"\nBackward Compatibility: {'PASS' if all_pass else 'FAIL'}")

    # Note about historical MRR
    print(f"\nNote: Historical Phase 3B reported MRR=0.940 (inflated by negatives getting MRR=1.0).")
    print(f"  The corrected positive-only MRR is 0.930, which matches the MRR reported in the")
    print(f"  abstention_gate.json (mrr_positive_only) from Phase 3B.")

    return all_pass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
