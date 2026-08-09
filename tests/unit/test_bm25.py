"""Tests for the deterministic Okapi BM25 index (roadmap 4.1)."""

from __future__ import annotations

from app.infrastructure.bm25 import BM25Index, tokenize


class TestTokenize:
    def test_lowercases_and_strips_punctuation(self) -> None:
        assert tokenize("Hello, WORLD!") == ["hello", "world"]

    def test_keeps_underscores_and_digits(self) -> None:
        assert tokenize("my_var 2x") == ["my_var", "2x"]

    def test_empty_and_punctuation_only(self) -> None:
        assert tokenize("") == []
        assert tokenize("!!??") == []


class TestBM25Index:
    def test_empty_corpus(self) -> None:
        assert BM25Index([]).search("python") == []

    def test_blank_query(self) -> None:
        index = BM25Index(["python is great"])
        assert index.search("") == []
        assert index.search("   ") == []

    def test_no_matching_terms(self) -> None:
        index = BM25Index(["python is great", "rust is fast"])
        assert index.search("zebra") == []

    def test_ranks_matching_doc_first(self) -> None:
        index = BM25Index(["python is great", "java is okay", "rust is fast"])
        result = index.search("python", top_k=3)
        assert result[0][0] == 0
        assert result[0][1] > 0.0

    def test_term_frequency_ranks_higher(self) -> None:
        index = BM25Index(
            ["python python python basics", "python intro"],
        )
        result = index.search("python", top_k=2)
        assert result[0][0] == 0

    def test_length_normalization_prefers_shorter(self) -> None:
        filler = " ".join(f"word{i}" for i in range(99))
        index = BM25Index(
            ["python zebra", f"python {filler}"],
        )
        result = index.search("python", top_k=2)
        assert result[0][0] == 0

    def test_idf_rare_term_weighs_more(self) -> None:
        corpus = ["python async", "python sync", "python only"]
        index = BM25Index(corpus)
        async_result = index.search("python async", top_k=3)
        # "async" appears in one doc; "python" in three; the async doc wins.
        assert async_result[0][0] == 0
        assert "async" in corpus[async_result[0][0]]

    def test_multiple_query_terms_sum(self) -> None:
        index = BM25Index(
            ["python async", "python threading", "async threads"],
        )
        result = index.search("python async", top_k=3)
        # Doc 0 contains both query terms; doc 1 and 2 contain one each.
        assert result[0][0] == 0

    def test_deterministic_ties(self) -> None:
        index = BM25Index(["python", "python", "python"])
        result = index.search("python", top_k=3)
        assert [i for i, _s in result] == [0, 1, 2]
        assert index.search("python", top_k=3) == result

    def test_top_k_respected(self) -> None:
        index = BM25Index(["python a", "python b", "python c"])
        assert len(index.search("python", top_k=2)) == 2

    def test_top_k_exceeds_corpus(self) -> None:
        index = BM25Index(["python a", "python b"])
        assert len(index.search("python", top_k=10)) == 2

    def test_non_positive_top_k(self) -> None:
        index = BM25Index(["python a"])
        assert index.search("python", top_k=0) == []
