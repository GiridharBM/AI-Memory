"""Tests for the Knowledge Engine (Milestone 4) features."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.domain.analysis import (
    Definition,
    DocumentAnalysis,
    DocumentSummary,
    ImportantEntity,
    KeyConcept,
    RelatedTopic,
)
from app.domain.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
)
from app.domain.semantic_chunking import DocumentChunk
from app.domain.vector_store import SearchResult, VectorEntry
from app.infrastructure.embeddings import EmbeddingResult
from app.infrastructure.knowledge_graph import KnowledgeGraphBuilder
from app.infrastructure.search import HybridSearch, SemanticSearch
from app.infrastructure.semantic_chunking import SemanticChunker
from app.infrastructure.vector_store import VectorStore, _cosine_similarity
from app.infrastructure.versioning import VersionManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        suggested_note_title="Test Note",
        summary=DocumentSummary(short="Short", detailed="Long"),
        keywords=["python", "testing"],
        categories=["Programming"],
        reading_time_minutes=5,
        difficulty="beginner",
        key_concepts=[
            KeyConcept(name="Pytest", explanation="Testing framework", importance="high"),
            KeyConcept(name="Coverage", explanation="Code coverage", importance="medium"),
        ],
        definitions=[Definition(term="Fixture", definition="Test setup helper")],
        important_entities=[
            ImportantEntity(name="Python", type="technology", description="Programming language"),
        ],
        tags=["test"],
        related_topics=[RelatedTopic(topic="TDD", reason="Related methodology")],
        suggested_related_notes=["Other Note"],
        suggested_backlinks=["Parent Note"],
    )


def _embedding(dims: int = 8) -> list[float]:
    return [float(i) / dims for i in range(dims)]


def _similar_embedding(dims: int = 8) -> list[float]:
    return [float(i + 0.1) / dims for i in range(dims)]


# ---------------------------------------------------------------------------
# Semantic Chunking
# ---------------------------------------------------------------------------

class TestSemanticChunking:
    def test_empty_text_returns_no_chunks(self) -> None:
        chunker = SemanticChunker()
        chunks = chunker.chunk("", "test.md", "markdown")
        assert chunks == []

    def test_short_text_single_chunk(self) -> None:
        chunker = SemanticChunker()
        chunks = chunker.chunk("Hello world", "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"
        assert chunks[0].source == "test.md"
        assert chunks[0].chunk_index == 0

    def test_heading_based_splitting(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=200)
        text = "# Title\n\nFirst section.\n\n## Subtitle\n\nSecond section."
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) >= 2

    def test_long_text_splits_by_size(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=100)
        text = ". ".join(f"Sentence {i}" for i in range(50))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) > 1

    def test_chunk_ids_are_unique(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=50)
        text = ". ".join(f"Sentence {i}" for i in range(20))
        chunks = chunker.chunk(text, "test.md", "markdown")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_metadata_preserves_source(self) -> None:
        chunker = SemanticChunker()
        chunks = chunker.chunk("Content", "doc.pdf", "pdf")
        assert chunks[0].source_type == "pdf"

    def test_overlap_chars(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=50, overlap_chars=10)
        text = ". ".join(f"Sentence {i}" for i in range(30))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) > 1

    def test_chunk_overlap_produces_shared_text(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=300, overlap_chars=200)
        text = ". ".join(f"Sentence {i}" for i in range(50))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) >= 2
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert previous.text[-200:] == current.text[:200]

    def test_chunk_overlap_single_chunk(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=2000, overlap_chars=200)
        chunks = chunker.chunk("Short text.", "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == "Short text."

    def test_chunk_overlap_offsets_preserved(self) -> None:
        text = ". ".join(f"Sentence {i}" for i in range(30))
        plain = SemanticChunker(max_chunk_chars=50, overlap_chars=0)
        overlapped = SemanticChunker(max_chunk_chars=50, overlap_chars=10)
        plain_chunks = plain.chunk(text, "test.md", "markdown")
        overlap_chunks = overlapped.chunk(text, "test.md", "markdown")
        assert len(plain_chunks) > 1
        assert [(c.start_char, c.end_char) for c in plain_chunks] == [
            (c.start_char, c.end_char) for c in overlap_chunks
        ]
        assert overlap_chunks[0].text == plain_chunks[0].text

    def test_chunk_overlap_zero(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=50, overlap_chars=0)
        text = ". ".join(f"Sentence {i}" for i in range(30))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) > 1
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert not current.text.startswith(previous.text[-1:])


# ---------------------------------------------------------------------------
# Duplicate Detection (existing)
# ---------------------------------------------------------------------------

class TestDuplicateDetectionExisting:
    def test_manifest_hash_lookup(self, tmp_path: Path) -> None:
        from app.infrastructure.state.manifest import ManifestManager
        manifest = ManifestManager(
            tmp_path / "manifest.json",
            project_root=tmp_path,
        )
        assert manifest.contains_hash("nonexistent") is False

    def test_manifest_add_and_contains(self, tmp_path: Path) -> None:
        from app.infrastructure.state.manifest import ManifestManager
        manifest = ManifestManager(
            tmp_path / "manifest.json",
            project_root=tmp_path,
        )
        manifest.add_processed_file(
            path=tmp_path / "test.md",
            sha256="abc123",
            extension=".md",
        )
        manifest.save()
        assert manifest.contains_hash("abc123") is True
        assert manifest.contains_hash("xyz") is False


# ---------------------------------------------------------------------------
# Wiki Linking (existing)
# ---------------------------------------------------------------------------

class TestWikiLinking:
    def test_wiki_link_generation(self) -> None:
        from app.templates.obsidian_note import _wiki_link
        assert _wiki_link("Python") == "[[Python]]"
        assert _wiki_link("Machine Learning") == "[[Machine Learning]]"

    def test_wiki_link_escapes_pipes(self) -> None:
        from app.templates.obsidian_note import _wiki_link
        result = _wiki_link("A|B")
        assert "\\|" in result
        assert result == "[[A\\|B]]"


# ---------------------------------------------------------------------------
# Backlinks (existing + new write_backlinks)
# ---------------------------------------------------------------------------

class TestBacklinks:
    def test_write_backlinks_creates_section(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        note_a = notes_dir / "Note A.md"
        note_a.write_text("---\ntitle: Note A\n---\nContent\n", encoding="utf-8")
        manager = WikiManager(tmp_path)
        updated = manager.write_backlinks("Note B.md", ["Note A"])
        assert updated == 1
        text = note_a.read_text(encoding="utf-8")
        assert "## Backlinks" in text
        assert "[[Note B" in text

    def test_write_backlinks_skips_existing(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        note_a = notes_dir / "Note A.md"
        note_a.write_text(
            "---\ntitle: Note A\n---\nContent\n\n## Backlinks\n\n- [[Old]]\n",
            encoding="utf-8",
        )
        manager = WikiManager(tmp_path)
        updated = manager.write_backlinks("Note B.md", ["Note A"])
        assert updated == 0

    def test_write_backlinks_no_titles(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        manager = WikiManager(tmp_path)
        updated = manager.write_backlinks("Note B.md", [])
        assert updated == 0


# ---------------------------------------------------------------------------
# Entity Extraction (existing via LLM)
# ---------------------------------------------------------------------------

class TestEntityExtraction:
    def test_entity_model_valid(self) -> None:
        entity = ImportantEntity(
            name="Python", type="technology", description="Language",
        )
        assert entity.name == "Python"
        assert entity.type == "technology"

    def test_entity_type_literal(self) -> None:
        for etype in ["person", "organization", "product", "project", "technology", "place", "paper", "concept", "other"]:
            entity = ImportantEntity(name="X", type=etype, description="Y")
            assert entity.type == etype


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------

class TestKnowledgeGraph:
    def test_add_node(self) -> None:
        g = KnowledgeGraph()
        n = KnowledgeNode(id="n1", label="A", node_type="concept")
        g.add_node(n)
        assert "n1" in g.nodes

    def test_add_edge_requires_nodes(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept"))
        g.add_node(KnowledgeNode(id="n2", label="B", node_type="concept"))
        g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert len(g.edges) == 1

    def test_add_edge_ignores_missing_nodes(self) -> None:
        g = KnowledgeGraph()
        g.add_edge(KnowledgeEdge(source_id="missing", target_id="also_missing", edge_type="related_to"))
        assert len(g.edges) == 0

    def test_add_edge_valid_endpoints_returns_true(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept"))
        g.add_node(KnowledgeNode(id="n2", label="B", node_type="concept"))
        added = g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert added is True
        assert len(g.edges) == 1

    def test_add_edge_missing_source_returns_false(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n2", label="B", node_type="concept"))
        added = g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert added is False
        assert len(g.edges) == 0

    def test_add_edge_missing_target_returns_false(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept"))
        added = g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert added is False
        assert len(g.edges) == 0

    def test_add_edge_both_missing_returns_false(self) -> None:
        g = KnowledgeGraph()
        added = g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert added is False
        assert len(g.edges) == 0

    def test_neighbors(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="a", label="A", node_type="concept"))
        g.add_node(KnowledgeNode(id="b", label="B", node_type="concept"))
        g.add_edge(KnowledgeEdge(source_id="a", target_id="b", edge_type="related_to"))
        neighbors = g.neighbors("a")
        assert len(neighbors) == 1
        assert neighbors[0][0].id == "b"

    def test_subgraph(self) -> None:
        g = KnowledgeGraph()
        for nid in ["a", "b", "c"]:
            g.add_node(KnowledgeNode(id=nid, label=nid, node_type="concept"))
        g.add_edge(KnowledgeEdge(source_id="a", target_id="b", edge_type="related_to"))
        g.add_edge(KnowledgeEdge(source_id="b", target_id="c", edge_type="related_to"))
        sub = g.subgraph("a", depth=1)
        assert "a" in sub.nodes
        assert "b" in sub.nodes
        assert "c" not in sub.nodes


class TestKnowledgeGraphBuilder:
    def test_build_from_analysis(self) -> None:
        builder = KnowledgeGraphBuilder()
        result = builder.build_from_analysis(_analysis(), "test.md")
        assert result.nodes_added > 0
        assert result.edges_added > 0
        assert len(result.graph.nodes) > 0

    def test_merge_graphs(self) -> None:
        g1 = KnowledgeGraph()
        g1.add_node(KnowledgeNode(id="a", label="A", node_type="concept"))
        g2 = KnowledgeGraph()
        g2.add_node(KnowledgeNode(id="b", label="B", node_type="concept"))
        builder = KnowledgeGraphBuilder()
        merged = builder.merge_graphs(g1, g2)
        assert "a" in merged.nodes
        assert "b" in merged.nodes


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

class TestEmbeddings:
    def test_embedding_result_dataclass(self) -> None:
        r = EmbeddingResult(model="test", embedding=[0.1, 0.2])
        assert r.model == "test"
        assert len(r.embedding) == 2

    def test_embedding_result_with_eval_count(self) -> None:
        r = EmbeddingResult(model="test", embedding=[0.1], prompt_eval_count=42)
        assert r.prompt_eval_count == 42

    def test_embedding_result_default_eval_count(self) -> None:
        r = EmbeddingResult(model="test", embedding=[0.1])
        assert r.prompt_eval_count is None


class TestEmbeddingService:
    def test_embed_empty_text_raises(self) -> None:
        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with pytest.raises(ValueError, match="empty"):
            svc.embed("")

    def test_embed_whitespace_only_raises(self) -> None:
        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with pytest.raises(ValueError, match="empty"):
            svc.embed("   ")

    def test_embed_batch_empty_returns_empty(self) -> None:
        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        assert svc.embed_batch([]) == []

    def test_embed_success(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "embeddings": [[0.1, 0.2, 0.3]],
            "prompt_eval_count": 10,
        }
        with patch.object(svc._client, "embed", return_value=mock_response) as m:
            result = svc.embed("hello world")
            m.assert_called_once_with(model="nomic-embed-text", input="hello world")
            assert result.model == "nomic-embed-text"
            assert result.embedding == [0.1, 0.2, 0.3]
            assert result.prompt_eval_count == 10

    def test_embed_no_model_dump(self) -> None:
        from unittest.mock import patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        raw_dict = {"embeddings": [[0.5, 0.6]], "prompt_eval_count": None}
        with patch.object(svc._client, "embed", return_value=raw_dict) as m:
            result = svc.embed("test")
            assert result.embedding == [0.5, 0.6]

    def test_embed_empty_embeddings_list(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"embeddings": []}
        with patch.object(svc._client, "embed", return_value=mock_response):
            result = svc.embed("test")
            assert result.embedding == []

    def test_embed_client_error_propagates(self) -> None:
        from unittest.mock import patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with patch.object(svc._client, "embed", side_effect=RuntimeError("connection")), \
             patch("app.infrastructure.embeddings.time.sleep"):
            with pytest.raises(RuntimeError, match="connection"):
                svc.embed("test")

    def test_embed_retry_on_transient_failure(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"embeddings": [[0.1, 0.2]]}
        calls = {"count": 0}

        def flaky(*args: object, **kwargs: object) -> MagicMock:
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("transient")
            return mock_response

        with patch.object(svc._client, "embed", side_effect=flaky) as m, \
             patch("app.infrastructure.embeddings.time.sleep") as sleep:
            result = svc.embed("hello")
        assert m.call_count == 3
        assert sleep.call_args_list[0].args[0] == 1.0
        assert sleep.call_args_list[1].args[0] == 2.0
        assert result.embedding == [0.1, 0.2]

    def test_embed_retry_exhausted(self) -> None:
        from unittest.mock import patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with patch.object(svc._client, "embed", side_effect=RuntimeError("fail")) as m, \
             patch("app.infrastructure.embeddings.time.sleep"):
            with pytest.raises(RuntimeError, match="fail"):
                svc.embed("test")
        assert m.call_count == 3

    def test_embed_batch_retry_on_transient_failure(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"embeddings": [[0.1, 0.2]]}
        calls = {"count": 0}

        def flaky(*args: object, **kwargs: object) -> MagicMock:
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("transient")
            return mock_response

        with patch.object(svc._client, "embed", side_effect=flaky) as m, \
             patch("app.infrastructure.embeddings.time.sleep"):
            results = svc.embed_batch(["a"])
        assert m.call_count == 3
        assert results[0].embedding == [0.1, 0.2]

    def test_embed_batch_success(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
        }
        with patch.object(svc._client, "embed", return_value=mock_response) as m:
            results = svc.embed_batch(["a", "b"])
            m.assert_called_once_with(model="nomic-embed-text", input=["a", "b"])
            assert len(results) == 2
            assert results[0].embedding == [0.1, 0.2]
            assert results[1].embedding == [0.3, 0.4]

    def test_embed_batch_client_error_propagates(self) -> None:
        from unittest.mock import patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with patch.object(svc._client, "embed", side_effect=RuntimeError("fail")), \
             patch("app.infrastructure.embeddings.time.sleep"):
            with pytest.raises(RuntimeError, match="fail"):
                svc.embed_batch(["a"])


# ---------------------------------------------------------------------------
# Vector Store
# ---------------------------------------------------------------------------

class TestVectorStore:
    def test_add_and_get(self) -> None:
        store = VectorStore()
        entry = VectorEntry(id="e1", text="hello", embedding=[1.0, 0.0, 0.0])
        store.add(entry)
        assert store.get("e1") is not None
        assert store.get("missing") is None
        assert len(store) == 1

    def test_remove(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="hello", embedding=[1.0]))
        assert store.remove("e1") is True
        assert store.get("e1") is None
        assert store.remove("e1") is False

    def test_search(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="cat", embedding=[1.0, 0.0, 0.0]))
        store.add(VectorEntry(id="e2", text="dog", embedding=[0.9, 0.1, 0.0]))
        store.add(VectorEntry(id="e3", text="car", embedding=[0.0, 0.0, 1.0]))
        results = store.search([1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].entry.id == "e1"

    def test_search_min_score(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="x", embedding=[0.0, 1.0]))
        results = store.search([1.0, 0.0], top_k=5, min_score=0.5)
        assert len(results) == 0

    def test_add_batch(self) -> None:
        store = VectorStore()
        entries = [
            VectorEntry(id=f"e{i}", text=f"text{i}", embedding=[float(i)])
            for i in range(5)
        ]
        store.add_batch(entries)
        assert len(store) == 5

    def test_persistence(self, tmp_path: Path) -> None:
        path = tmp_path / "vectors.json"
        store1 = VectorStore(persistence_path=path)
        store1.add(VectorEntry(id="e1", text="hello", embedding=[1.0, 0.5]))
        store1.save()
        store2 = VectorStore(persistence_path=path)
        assert len(store2) == 1
        assert store2.get("e1").text == "hello"


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_different_lengths(self) -> None:
        assert _cosine_similarity([1.0], [1.0, 0.0]) == 0.0

    def test_zero_vector(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# Semantic Search
# ---------------------------------------------------------------------------

class TestSemanticSearch:
    def test_search_returns_hits(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python is great", embedding=[1.0, 0.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java is okay", embedding=[0.9, 0.1, 0.0]))
        store.add(VectorEntry(id="e3", text="rust is fast", embedding=[0.0, 0.0, 1.0]))
        ss = SemanticSearch(store)
        results = ss.search([1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].text == "python is great"
        assert results[0].score > results[1].score

    def test_empty_store(self) -> None:
        ss = SemanticSearch(VectorStore())
        assert ss.search([1.0, 0.0], top_k=5) == []


class TestHybridSearch:
    def test_hybrid_weights_semantic_more(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python testing framework", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java enterprise", embedding=[0.9, 0.1]))
        hs = HybridSearch(store)
        results = hs.search("python testing", [1.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].entry_id == "e1"


# ---------------------------------------------------------------------------
# Version History
# ---------------------------------------------------------------------------

class TestVersionHistory:
    def test_record_version(self, tmp_path: Path) -> None:
        vm = VersionManager(tmp_path)
        entry = vm.record_version("Note.md", "# Content v1", source="test.md")
        assert entry.version == 1
        assert vm.has_versions("Note.md") is True

    def test_record_version_populates_sha256(self, tmp_path: Path) -> None:
        vm = VersionManager(tmp_path)

        content = "# Content v1"
        entry = vm.record_version("Note.md", content)
        assert entry.sha256 == hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert vm.get_versions("Note.md")[0].sha256 == entry.sha256

    def test_multiple_versions(self, tmp_path: Path) -> None:
        vm = VersionManager(tmp_path)
        vm.record_version("Note.md", "v1")
        vm.record_version("Note.md", "v2")
        vm.record_version("Note.md", "v3")
        versions = vm.get_versions("Note.md")
        assert len(versions) == 3
        assert versions[2].version == 3

    def test_get_version_content(self, tmp_path: Path) -> None:
        vm = VersionManager(tmp_path)
        vm.record_version("Note.md", "# Hello")
        content = vm.get_version_content("Note.md", 1)
        assert content == "# Hello"

    def test_get_nonexistent_version(self, tmp_path: Path) -> None:
        vm = VersionManager(tmp_path)
        assert vm.get_version_content("Note.md", 99) is None

    def test_no_versions(self, tmp_path: Path) -> None:
        vm = VersionManager(tmp_path)
        assert vm.has_versions("Unknown.md") is False
        assert vm.get_versions("Unknown.md") == []


# ---------------------------------------------------------------------------
# Domain model integration
# ---------------------------------------------------------------------------

class TestDomainIntegration:
    def test_document_chunk_dataclass(self) -> None:
        c = DocumentChunk(
            chunk_id="c1", text="hello", source="t.md",
            source_type="markdown", chunk_index=0, start_char=0, end_char=5,
        )
        assert c.text == "hello"
        assert c.chunk_index == 0

    def test_vector_entry_dataclass(self) -> None:
        e = VectorEntry(id="e1", text="hello", embedding=[0.1])
        assert e.id == "e1"

    def test_search_result_dataclass(self) -> None:
        e = VectorEntry(id="e1", text="hello", embedding=[0.1])
        r = SearchResult(entry=e, score=0.95)
        assert r.score == 0.95


# ---------------------------------------------------------------------------
# Knowledge Graph Persistence
# ---------------------------------------------------------------------------

class TestKnowledgeGraphPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.json"
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept", source="t.md"))
        g.add_node(KnowledgeNode(id="n2", label="B", node_type="entity", source="t.md"))
        g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to", weight=0.8))
        g.save(path)

        loaded = KnowledgeGraph.load(path)
        assert len(loaded.nodes) == 2
        assert "n1" in loaded.nodes
        assert "n2" in loaded.nodes
        assert len(loaded.edges) == 1
        assert loaded.edges[0].weight == 0.8

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "graph.json"
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="X", node_type="note"))
        g.save(path)
        assert path.exists()

    def test_load_empty_graph(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text('{"nodes": [], "edges": []}', encoding="utf-8")
        g = KnowledgeGraph.load(path)
        assert len(g.nodes) == 0
        assert len(g.edges) == 0

    def test_merge_and_persist(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.json"
        g1 = KnowledgeGraph()
        g1.add_node(KnowledgeNode(id="a", label="A", node_type="concept"))
        g1.save(path)

        g2 = KnowledgeGraph()
        g2.add_node(KnowledgeNode(id="b", label="B", node_type="entity"))

        builder = KnowledgeGraphBuilder()
        existing = KnowledgeGraph.load(path)
        merged = builder.merge_graphs(existing, g2)
        merged.save(path)

        final = KnowledgeGraph.load(path)
        assert "a" in final.nodes
        assert "b" in final.nodes


# ---------------------------------------------------------------------------
# Placeholder Notes
# ---------------------------------------------------------------------------

class TestPlaceholderNotes:
    def test_create_placeholder(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        manager = WikiManager(tmp_path)
        path = manager.create_placeholder("Quantum Computing", "Physics Note")
        assert path is not None
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "Quantum Computing" in text
        assert "Physics Note" in text
        assert "## Backlinks" in text

    def test_create_placeholder_no_duplicate(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        manager = WikiManager(tmp_path)
        path1 = manager.create_placeholder("Test", "Source")
        path2 = manager.create_placeholder("Test", "Source")
        assert path1 is not None
        assert path2 is None

    def test_placeholder_has_stub_tag(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        manager = WikiManager(tmp_path)
        path = manager.create_placeholder("My Topic", "Parent")
        text = path.read_text(encoding="utf-8")
        assert "stub" in text
        assert "auto-generated" in text

    def test_vault_writer_create_placeholder(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.writer import VaultWriter
        writer = VaultWriter(tmp_path)
        writer.create_placeholder("Test Note", "Source Note")
        note_path = tmp_path / "Notes" / "Test Note.md"
        assert note_path.exists()


# ---------------------------------------------------------------------------
# Pipeline Integration (mocked)
# ---------------------------------------------------------------------------

class TestPipelineKnowledgeEngine:
    def test_workflow_result_has_kg_fields(self) -> None:
        from app.domain.documents import DocumentMetadata, SourceDocument
        from app.domain.notes import ObsidianNote
        from app.infrastructure.vault.wiki_manager import WikiUpdateResult
        from app.pipelines.ingest_workflow import IngestionWorkflowResult

        doc = SourceDocument(
            source="t.md", filename="t.md", source_type="text", text="x",
            metadata=DocumentMetadata(),
        )
        from unittest.mock import MagicMock
        ai = MagicMock()
        ai.analysis = _analysis()
        from datetime import UTC, datetime
        note = ObsidianNote(
            title="T", filename="t.md", source="t.md", markdown="# T",
            generated_at=datetime.now(tz=UTC), source_type="text",
        )
        wr = WikiUpdateResult(note_path=Path("t.md"), created=True, updated=False,
                              index_path=Path("i.md"), overview_path=Path("o.md"),
                              log_path=Path("l.md"))

        result = IngestionWorkflowResult(
            document=doc, ai_result=ai, note=note, write_result=wr,
        )
        assert result.knowledge_graph is None
        assert result.chunks_stored == 0
        assert result.cross_links_added == 0

    def test_workflow_accepts_kg_params(self) -> None:
        from unittest.mock import MagicMock

        from app.pipelines.ingest_workflow import IngestionWorkflow

        writer = MagicMock()
        writer.save.return_value = MagicMock(
            note_path=Path("t.md"), created=True, updated=False,
            index_path=Path("i.md"), overview_path=Path("o.md"),
            log_path=Path("l.md"),
        )
        ollama = MagicMock()
        wf = IngestionWorkflow(
            ingestion_service=MagicMock(),
            ollama_client=ollama,
            note_generator=MagicMock(),
            writer=writer,
            chunker=MagicMock(),
            embedding_service=MagicMock(),
            vector_store=MagicMock(),
            knowledge_graph_builder=MagicMock(),
        )
        assert wf._chunker is not None
        assert wf._vector_store is not None

    def test_knowledge_engine_skips_when_no_components(self) -> None:
        from unittest.mock import MagicMock

        from app.domain.documents import DocumentMetadata, SourceDocument
        from app.pipelines.ingest_workflow import IngestionWorkflow

        writer = MagicMock()
        wf = IngestionWorkflow(
            ingestion_service=MagicMock(),
            ollama_client=MagicMock(),
            note_generator=MagicMock(),
            writer=writer,
        )
        doc = SourceDocument(
            source="t.md", filename="t.md", source_type="text", text="hello",
            metadata=DocumentMetadata(),
        )
        kg, stored, links = wf._run_knowledge_engine(doc, _analysis())
        assert kg is None
        assert stored == 0
        assert links == 0


# ---------------------------------------------------------------------------
# Cross-Document Linking
# ---------------------------------------------------------------------------

class TestCrossDocumentLinking:
    def test_find_similar_chunks(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="doc1::chunk_0", text="python is a programming language",
            embedding=[0.9, 0.1, 0.0], source="doc1.py",
        ))
        store.add(VectorEntry(
            id="doc2::chunk_0", text="python is widely used in data science",
            embedding=[0.85, 0.15, 0.0], source="doc2.md",
        ))

        from app.infrastructure.search import SemanticSearch
        search = SemanticSearch(store)
        query_emb = [0.88, 0.12, 0.0]
        hits = search.search(query_emb, top_k=3, min_score=0.7)
        sources = {h.source for h in hits}
        assert len(hits) >= 2
        assert "doc1.py" in sources
        assert "doc2.md" in sources

    def test_no_cross_links_for_identical_source(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="doc1::chunk_0", text="hello world",
            embedding=[1.0, 0.0], source="doc1.md",
        ))
        store.add(VectorEntry(
            id="doc1::chunk_1", text="hello world again",
            embedding=[0.95, 0.05], source="doc1.md",
        ))

        from app.infrastructure.search import SemanticSearch
        search = SemanticSearch(store)
        hits = search.search([1.0, 0.0], top_k=5, min_score=0.7)
        different_source = [h for h in hits if h.source != "doc1.md"]
        assert len(different_source) == 0
