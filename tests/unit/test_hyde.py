"""Unit tests for HyDE transform (Phase 3E)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.infrastructure.hyde import HyDETransform


def _make_generate(response: str | None = None, side_effect: Exception | None = None):
    gen = MagicMock(return_value=response)
    if side_effect is not None:
        gen.side_effect = side_effect
    return gen


class TestHyDETransform:
    def test_transform_returns_hypothetical_answer(self):
        gen = _make_generate("PAM uses a vector store for embeddings.")
        h = HyDETransform(gen)
        result = h.transform("How does PAM store embeddings?")
        assert result == "PAM uses a vector store for embeddings."
        gen.assert_called_once()

    def test_transform_strips_whitespace(self):
        gen = _make_generate("  The answer is 42.  \n")
        h = HyDETransform(gen)
        result = h.transform("What is the answer?")
        assert result == "The answer is 42."

    def test_transform_truncates_to_max_length(self):
        gen = _make_generate("A" * 1000)
        h = HyDETransform(gen, max_length=100)
        result = h.transform("test query")
        assert len(result) == 100

    def test_transform_returns_none_on_empty_response(self):
        gen = _make_generate("")
        h = HyDETransform(gen)
        assert h.transform("test query") is None

    def test_transform_returns_none_on_whitespace_only_response(self):
        gen = _make_generate("   \n  ")
        h = HyDETransform(gen)
        assert h.transform("test query") is None

    def test_transform_returns_none_on_llm_failure(self):
        gen = _make_generate(side_effect=RuntimeError("LLM unavailable"))
        h = HyDETransform(gen)
        assert h.transform("test query") is None

    def test_transform_returns_none_on_timeout(self):
        gen = _make_generate(side_effect=TimeoutError("timed out"))
        h = HyDETransform(gen)
        assert h.transform("test query") is None

    def test_transform_passes_system_prompt(self):
        gen = _make_generate("Answer text.")
        h = HyDETransform(gen)
        h.transform("my query")
        call_args = gen.call_args
        assert "answer" in call_args[0][0].lower()

    def test_transform_passes_query_as_user_prompt(self):
        gen = _make_generate("Answer text.")
        h = HyDETransform(gen)
        h.transform("What is PAM?")
        call_args = gen.call_args
        assert call_args[0][1] == "What is PAM?"

    def test_default_max_length_is_500(self):
        gen = _make_generate("X" * 600)
        h = HyDETransform(gen)
        result = h.transform("test")
        assert len(result) == 500


class TestHyDESearchIntegration:
    """Experiment 4: HyDE failure/fallback at the SearchService level."""

    def test_no_hyde_call_when_disabled(self):
        """When hyde=None, search uses original query for embedding."""
        from app.infrastructure.search import SearchService, VectorStore

        embed_fn = MagicMock(return_value=[0.1] * 768)
        store = MagicMock(spec=VectorStore)
        store.search.return_value = []
        svc = SearchService(store, embed=embed_fn, hyde=None)
        svc.search("test query", top_k=5)
        embed_fn.assert_called_once_with("test query")

    def test_hyde_used_when_enabled(self):
        """When hyde is set, the hyde-transformed text is embedded, not the query."""
        from app.infrastructure.search import SearchService, VectorStore

        embed_fn = MagicMock(return_value=[0.1] * 768)
        hyde = MagicMock(spec=HyDETransform)
        hyde.transform.return_value = "HyDE answer text"
        store = MagicMock(spec=VectorStore)
        store.search.return_value = []
        svc = SearchService(store, embed=embed_fn, hyde=hyde)
        svc.search("original query", top_k=5)
        hyde.transform.assert_called_once_with("original query")
        embed_fn.assert_called_once_with("HyDE answer text")

    def test_hyde_fallback_to_original_on_failure(self):
        """When hyde.transform returns None, original query is embedded."""
        from app.infrastructure.search import SearchService, VectorStore

        embed_fn = MagicMock(return_value=[0.1] * 768)
        hyde = MagicMock(spec=HyDETransform)
        hyde.transform.return_value = None
        store = MagicMock(spec=VectorStore)
        store.search.return_value = []
        svc = SearchService(store, embed=embed_fn, hyde=hyde)
        svc.search("fallback query", top_k=5)
        embed_fn.assert_called_once_with("fallback query")

    def test_bm25_still_receives_original_query(self):
        """HyDE only changes the embedding; original query is still passed to HybridSearch."""
        from app.infrastructure.search import SearchService, VectorStore

        embed_fn = MagicMock(return_value=[0.1] * 768)
        hyde = MagicMock(spec=HyDETransform)
        hyde.transform.return_value = "HyDE transformed text"
        store = MagicMock(spec=VectorStore)
        store.search.return_value = []
        svc = SearchService(store, embed=embed_fn, hyde=hyde)
        svc.search("original query", top_k=5)
        # HyDE was called with original query
        hyde.transform.assert_called_once_with("original query")
        # Embed was called with HyDE text (not original query)
        embed_fn.assert_called_once_with("HyDE transformed text")
        # store.search was called with the HyDE-derived embedding
        store.search.assert_called_once()
        dense_call_embedding = store.search.call_args[0][0]
        assert dense_call_embedding == [0.1] * 768

    def test_empty_query_returns_empty(self):
        """Empty query bypasses everything."""
        from app.infrastructure.search import SearchService, VectorStore

        embed_fn = MagicMock()
        hyde = MagicMock(spec=HyDETransform)
        store = MagicMock(spec=VectorStore)
        svc = SearchService(store, embed=embed_fn, hyde=hyde)
        result = svc.search("", top_k=5)
        assert result == []
        hyde.transform.assert_not_called()
        embed_fn.assert_not_called()
