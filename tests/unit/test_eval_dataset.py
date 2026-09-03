"""Tests for the PAM V1 evaluation dataset and metrics (Phase 3D)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parent.parent.parent / "eval"
DATASET_PATH = EVAL_DIR / "datasets" / "dataset.json"
FROZEN_V1_PATH = EVAL_DIR / "datasets" / "dataset_v1_frozen.json"

# Source matching (inlined from run_eval.py to avoid heavy PAM imports)
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


def compute_metrics(results: list[dict], ks: list[int] | None = None) -> dict:
    if ks is None:
        ks = [1, 3, 5, 10]
    total = len(results)
    if total == 0:
        return {"error": "no results"}
    positive_results = [r for r in results if r["expected_sources"]]
    negative_results = [r for r in results if not r["expected_sources"]]
    hit_rates = {k: 0 for k in ks}
    mrr_scores = []
    for r in results:
        expected = r["expected_sources"]
        retrieved_sources = [hit["source"] for hit in r["hits"]]
        if not expected:
            continue
        found_at_rank = None
        for rank, src in enumerate(retrieved_sources, 1):
            if match_source(src, expected):
                found_at_rank = rank
                break
        for k in ks:
            if found_at_rank is not None and found_at_rank <= k:
                hit_rates[k] += 1
        mrr_scores.append(1.0 / found_at_rank if found_at_rank else 0.0)
    n_pos = len(positive_results)
    metrics: dict = {"total_queries": total, "queries_with_ground_truth": n_pos, "negative_queries": len(negative_results)}
    for k in ks:
        metrics[f"hit_rate@{k}"] = hit_rates[k] / n_pos if n_pos else 0
    metrics["mrr"] = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0
    return metrics


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def dataset() -> dict:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def queries(dataset: dict) -> list[dict]:
    return dataset["queries"]


@pytest.fixture(scope="module")
def frozen_v1() -> dict:
    with open(FROZEN_V1_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Dataset size tests ────────────────────────────────────────────────


class TestDatasetSize:
    def test_total_queries_at_least_150(self, queries: list[dict]) -> None:
        assert len(queries) >= 150, f"Expected >= 150 queries, got {len(queries)}"

    def test_total_queries_exactly_160(self, queries: list[dict]) -> None:
        assert len(queries) == 160, f"Expected 160 queries, got {len(queries)}"

    def test_negative_queries_at_least_25(self, queries: list[dict]) -> None:
        neg = [q for q in queries if not q["expected_sources"]]
        assert len(neg) >= 25, f"Expected >= 25 negatives, got {len(neg)}"

    def test_negative_queries_count(self, queries: list[dict]) -> None:
        neg = [q for q in queries if not q["expected_sources"]]
        assert len(neg) == 37, f"Expected 37 negatives, got {len(neg)}"


# ── ID uniqueness tests ──────────────────────────────────────────────


class TestQueryIDs:
    def test_no_duplicate_ids(self, queries: list[dict]) -> None:
        ids = [q["id"] for q in queries]
        assert len(ids) == len(set(ids)), "Duplicate query IDs found"

    def test_id_format(self, queries: list[dict]) -> None:
        for q in queries:
            assert q["id"].startswith("q"), f"ID {q['id']} does not start with 'q'"
            num = q["id"][1:]
            assert num.isdigit(), f"ID {q['id']} has non-numeric suffix"


# ── Category structure tests ─────────────────────────────────────────


class TestCategories:
    VALID = {"factoid", "comparison", "negative", "cross_document", "tricky"}

    def test_all_categories_valid(self, queries: list[dict]) -> None:
        for q in queries:
            assert q["category"] in self.VALID, f"{q['id']}: invalid category '{q['category']}'"

    def test_no_category_below_minimum(self, queries: list[dict]) -> None:
        cats = {}
        for q in queries:
            cats[q["category"]] = cats.get(q["category"], 0) + 1
        for cat, count in cats.items():
            assert count >= 5, f"Category '{cat}' has only {count} queries (minimum 5)"

    def test_negatives_are_own_category(self, queries: list[dict]) -> None:
        for q in queries:
            if not q["expected_sources"]:
                assert q["category"] == "negative", (
                    f"{q['id']}: empty sources but category is '{q['category']}'"
                )


# ── Positive ground truth tests ──────────────────────────────────────


class TestPositiveGroundTruth:
    def test_positive_queries_have_sources(self, queries: list[dict]) -> None:
        for q in queries:
            if q["category"] != "negative":
                assert q["expected_sources"], f"{q['id']}: positive query has no expected_sources"

    def test_positive_queries_have_evidence(self, queries: list[dict]) -> None:
        for q in queries:
            if q["category"] != "negative":
                assert q.get("expected_evidence"), f"{q['id']}: positive query has no expected_evidence"

    def test_all_source_keys_known(self, queries: list[dict]) -> None:
        for q in queries:
            for src in q.get("expected_sources", []):
                assert src in SOURCE_KEY_TO_FILENAME or src in {
                    "neural_networks", "daa_assignment", "jharkhand_protest",
                    "gpt56_demo", "openhands", "utthunga", "pcb_design",
                    "leetcode", "tihan", "b_md", "pam_smoke_test", "sigmamusicart",
                }, f"{q['id']}: unknown source key '{src}'"


# ── Negative ground truth tests ──────────────────────────────────────


class TestNegativeGroundTruth:
    def test_negative_queries_have_empty_sources(self, queries: list[dict]) -> None:
        for q in queries:
            if q["category"] == "negative":
                assert not q["expected_sources"], (
                    f"{q['id']}: negative query has non-empty expected_sources"
                )

    def test_negative_queries_have_null_evidence(self, queries: list[dict]) -> None:
        for q in queries:
            if q["category"] == "negative":
                evidence = q.get("expected_evidence")
                assert evidence is None or evidence == "", (
                    f"{q['id']}: negative query has non-null expected_evidence"
                )


# ── MRR calculation tests ────────────────────────────────────────────


class TestMRRBugFix:
    def test_negative_queries_excluded_from_mrr(self) -> None:
        """Negative queries must not contribute to MRR (the Phase 3D bug fix)."""
        results = [
            {
                "id": "pos1",
                "expected_sources": ["utthunga"],
                "hits": [{"source": "Our Organization.md", "score": 0.9}],
                "matched": True,
                "category": "factoid",
            },
            {
                "id": "pos2",
                "expected_sources": ["openhands"],
                "hits": [{"source": "unrelated.md", "score": 0.9}],
                "matched": False,
                "category": "factoid",
            },
            {
                "id": "neg1",
                "expected_sources": [],
                "hits": [{"source": "something.md", "score": 0.9}],
                "matched": False,
                "category": "negative",
            },
        ]
        metrics = compute_metrics(results)
        # MRR should be (1.0/1 + 0.0) / 2 = 0.5, NOT (1.0/1 + 0.0 + 1.0) / 3
        assert metrics["mrr"] == pytest.approx(0.5), (
            f"Negative query incorrectly included in MRR: {metrics['mrr']}"
        )

    def test_only_positive_queries_in_mrr(self) -> None:
        """MRR denominator should be count of positive queries only."""
        results = [
            {
                "id": "pos1",
                "expected_sources": ["utthunga"],
                "hits": [{"source": "Our Organization.md", "score": 0.9}],
                "matched": True,
                "category": "factoid",
            },
            {
                "id": "neg1",
                "expected_sources": [],
                "hits": [{"source": "something.md", "score": 0.9}],
                "matched": False,
                "category": "negative",
            },
            {
                "id": "neg2",
                "expected_sources": [],
                "hits": [{"source": "other.md", "score": 0.9}],
                "matched": False,
                "category": "negative",
            },
        ]
        metrics = compute_metrics(results)
        assert metrics["mrr"] == pytest.approx(1.0), (
            f"MRR with 1 positive found at rank 1 should be 1.0, got {metrics['mrr']}"
        )


# ── Source matching tests ────────────────────────────────────────────


class TestSourceMatching:
    def test_exact_match(self) -> None:
        assert match_source("Our Organization.md", ["utthunga"])

    def test_substring_match(self) -> None:
        assert match_source("OpenHands An Open Platform.md", ["openhands"])

    def test_no_match(self) -> None:
        assert not match_source("random_file.md", ["utthunga"])

    def test_normalize_source_strips_path(self) -> None:
        assert normalize_source("D:\\path\\to\\file.md") == "file.md"

    def test_normalize_source_strips_unix_path(self) -> None:
        assert normalize_source("/path/to/file.md") == "file.md"

    def test_all_source_keys_have_mapping(self) -> None:
        all_keys = {
            "neural_networks", "daa_assignment", "jharkhand_protest", "gpt56_demo",
            "openhands", "utthunga", "pcb_design", "leetcode", "tihan", "b_md",
            "pam_smoke_test", "sigmamusicart",
        }
        for key in all_keys:
            assert key in SOURCE_KEY_TO_FILENAME, f"Source key '{key}' missing from mapping"


# ── Frozen v1 reference tests ─────────────────────────────────────────


class TestFrozenV1Reference:
    def test_frozen_v1_exists(self) -> None:
        assert FROZEN_V1_PATH.exists(), f"Frozen v1 dataset not found at {FROZEN_V1_PATH}"

    def test_frozen_v1_has_50_queries(self, frozen_v1: dict) -> None:
        assert len(frozen_v1["queries"]) == 50

    def test_frozen_v1_is_marked_frozen(self, frozen_v1: dict) -> None:
        assert frozen_v1.get("_frozen") is True

    def test_frozen_v1_has_original_queries(self, frozen_v1: dict) -> None:
        ids = [q["id"] for q in frozen_v1["queries"]]
        assert "q001" in ids
        assert "q050" in ids


# ── Dataset integrity tests ──────────────────────────────────────────


class TestDatasetIntegrity:
    def test_metadata_version(self, dataset: dict) -> None:
        assert dataset["metadata"]["version"] == "2.0"

    def test_metadata_has_phase(self, dataset: dict) -> None:
        assert dataset["metadata"].get("phase") == "3D"

    def test_metadata_references_frozen(self, dataset: dict) -> None:
        assert "dataset_v1_frozen.json" in dataset["metadata"].get("original_frozen_as", "")

    def test_all_queries_have_required_fields(self, queries: list[dict]) -> None:
        required = {"id", "query", "expected_sources", "category", "difficulty", "ground_truth_reliable"}
        for q in queries:
            missing = required - set(q.keys())
            assert not missing, f"{q.get('id', '?')}: missing fields {missing}"

    def test_difficulty_values_valid(self, queries: list[dict]) -> None:
        valid = {"easy", "medium", "hard"}
        for q in queries:
            assert q["difficulty"] in valid, f"{q['id']}: invalid difficulty '{q['difficulty']}'"
