"""P3-106 integration: chunking engine parity through ``IngestionWorkflow``.

A real markdown document is chunked inside the ingestion pipeline with the
``"auto"`` and ``"heuristic"`` engine selections. When nltk is absent, ``"auto"``
resolves to the heuristic engine, so the chunk counts must be identical; when
nltk is installed (``"auto"`` -> ``punkt_tab``), the segmentations are allowed
to differ and only a successful, non-empty, deterministic run is asserted.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis, DocumentSummary, KeyConcept
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.semantic_chunking import ChunkingPolicy, SemanticChunker
from app.infrastructure.sentence_tokenizer import (
    SentenceTokenizerSelectionError,
    get_sentence_tokenizer,
)
from app.pipelines.ingest_workflow import IngestionWorkflow

pytestmark = pytest.mark.integration


class FakeEmbeddingService:
    """Deterministic fake embeddings — no live Ollama required."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    def _text_to_vector(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        rng = random.Random(h[:8])
        vec = [rng.gauss(0, 1) for _ in range(self._dim)]
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm > 0 else vec

    def embed(self, text: str) -> Any:
        from app.infrastructure.embeddings import EmbeddingResult

        return EmbeddingResult(model="fake-embed", embedding=self._text_to_vector(text))

    def embed_batch(self, texts: list[str]) -> list[Any]:
        return [self.embed(t) for t in texts]


def _nltk_available() -> bool:
    try:
        get_sentence_tokenizer("nltk")
    except SentenceTokenizerSelectionError:
        return False
    return True


def _document(source: str, text: str) -> SourceDocument:
    return SourceDocument(
        source=source,
        source_path=None,
        source_type="markdown",
        filename=source,
        text=text,
        metadata=DocumentMetadata(title="Test"),
    )


def _analysis(note_title: str, concept: str) -> DocumentAnalysis:
    return DocumentAnalysis(
        suggested_note_title=note_title,
        summary=DocumentSummary(short="Short", detailed="Detailed"),
        key_concepts=[
            KeyConcept(name=concept, explanation="explanation", importance="high"),
        ],
    )


def _markdown_doc() -> str:
    """A real-ish markdown page whose long section forces sentence-level
    splitting (> ``max_chunk_chars``) in the pipeline."""
    paragraphs = []
    for n in range(3):
        sentences = " ".join(
            f"Sentence {j} of paragraph {n} about the system's features." for j in range(30)
        )
        paragraphs.append(f"Paragraph {n}: {sentences}")
    return "# Personal Knowledge Base\n\n## Introduction\n\n" + "\n\n".join(paragraphs)


def _chunk_count(settings: Settings, engine: str) -> int:
    settings.chunking.sentence_tokenizer = engine
    workflow = IngestionWorkflow.create_default(settings)
    workflow._embedding_service = FakeEmbeddingService()
    _, stored, _ = workflow._run_knowledge_engine(
        _document("doc.md", _markdown_doc()),
        _analysis("Doc", "Concept"),
    )
    return stored


def test_auto_and_heuristic_engine_parity(tmp_settings: Settings) -> None:
    auto_count = _chunk_count(tmp_settings, "auto")
    heuristic_count = _chunk_count(tmp_settings, "heuristic")
    assert auto_count > 0
    assert heuristic_count > 0
    if not _nltk_available():
        assert auto_count == heuristic_count


def test_heuristic_engine_deterministic_through_pipeline(tmp_settings: Settings) -> None:
    first = _chunk_count(tmp_settings, "heuristic")
    second = _chunk_count(tmp_settings, "heuristic")
    assert first == second
    assert first > 0


def test_hierarchical_heading_metadata_through_pipeline(tmp_settings: Settings) -> None:
    """P3-201: heading hierarchy metadata attached to chunks survives the
    ingestion pipeline and lands on the stored vector entries."""
    tmp_settings.chunking.sentence_tokenizer = "heuristic"
    workflow = IngestionWorkflow.create_default(tmp_settings)
    workflow._embedding_service = FakeEmbeddingService()
    _, stored, _ = workflow._run_knowledge_engine(
        _document("hier.md", "# Top\n\n## Sub\n\nBody text here."),
        _analysis("Doc", "Concept"),
    )
    assert stored == 2
    entries = list(workflow._vector_store._entries.values())
    assert [e.metadata["heading_path"] for e in entries] == ["Top", "Top/Sub"]
    assert [e.metadata["parent_heading"] for e in entries] == ["", "Top"]
    assert [e.metadata["heading_level"] for e in entries] == ["1", "2"]


def test_list_block_through_pipeline(tmp_settings: Settings) -> None:
    """P3-202: a long markdown list with blank lines between items splits at
    whole-item boundaries through the ingestion pipeline — every stored entry
    is made of whole items, never sentence-split fragments."""
    tmp_settings.chunking.sentence_tokenizer = "heuristic"
    workflow = IngestionWorkflow.create_default(tmp_settings)
    workflow._embedding_service = FakeEmbeddingService()
    workflow._chunker = SemanticChunker(max_chunk_chars=60, overlap_chars=0)
    items = [
        f"- Item {n} has several sentences with plenty of words here to exceed "
        f"the chunk budget. Tail {n}."
        for n in range(40)
    ]
    list_text = "\n\n".join(items)
    _, stored, _ = workflow._run_knowledge_engine(
        _document("list.md", "# List Doc\n\n" + list_text),
        _analysis("Doc", "Concept"),
    )
    entries = list(workflow._vector_store._entries.values())
    assert stored == len(entries) > 2
    list_entries = [e for e in entries if e.text.startswith("- Item ")]
    assert len(list_entries) > 1
    for entry in list_entries:
        assert entry.text.split("\n")  # non-empty
        for line in entry.text.split("\n"):
            assert line in items


def test_code_block_through_pipeline(tmp_settings: Settings) -> None:
    """P3-203: a fenced code block stays atomic through the ingestion pipeline
    — one verbatim entry with its language metadata, prose untouched around it."""
    tmp_settings.chunking.sentence_tokenizer = "heuristic"
    workflow = IngestionWorkflow.create_default(tmp_settings)
    workflow._embedding_service = FakeEmbeddingService()
    code = "```python\nimport os\n\nos.getcwd()\n```"
    _, stored, _ = workflow._run_knowledge_engine(
        _document(
            "code.md",
            "# Code Doc\n\nSome prose paragraph.\n\n" + code + "\n\nOutro prose.",
        ),
        _analysis("Doc", "Concept"),
    )
    entries = list(workflow._vector_store._entries.values())
    assert stored == len(entries) >= 3
    code_entries = [e for e in entries if e.metadata.get("language") == "python"]
    assert len(code_entries) == 1
    assert code_entries[0].text == code
    assert code_entries[0].metadata["heading"] == "Code Doc"
    assert all(
        "language" not in e.metadata for e in entries if e is not code_entries[0]
    )


def test_structured_content_through_pipeline(tmp_settings: Settings) -> None:
    """P3-204: a markdown table, a callout blockquote, and a definition list stay
    atomic through the ingestion pipeline — one verbatim entry each with its
    structure metadata, prose untouched around them."""
    tmp_settings.chunking.sentence_tokenizer = "heuristic"
    workflow = IngestionWorkflow.create_default(tmp_settings)
    workflow._embedding_service = FakeEmbeddingService()
    workflow._chunker = SemanticChunker(max_chunk_chars=200, overlap_chars=0)
    table = "| Name | Value |\n|---|---|\n| alpha | 1 |\n| beta | 2 |"
    callout = "> [!NOTE] Check this.\n> Second line."
    definition = "Term\n: A definition."
    _, stored, _ = workflow._run_knowledge_engine(
        _document(
            "structured.md",
            "# Structured Doc\n\nProse paragraph.\n\n"
            + table
            + "\n\n"
            + callout
            + "\n\n"
            + definition,
        ),
        _analysis("Doc", "Concept"),
    )
    entries = list(workflow._vector_store._entries.values())
    assert stored == len(entries) >= 4
    table_entries = [
        e for e in entries if e.metadata.get("structure_type") == "table"
    ]
    callout_entries = [
        e for e in entries if e.metadata.get("structure_type") == "callout"
    ]
    definition_entries = [
        e for e in entries if e.metadata.get("structure_type") == "definition_list"
    ]
    assert len(table_entries) == 1
    assert table_entries[0].text == table
    assert table_entries[0].metadata["heading"] == "Structured Doc"
    assert len(callout_entries) == 1
    assert callout_entries[0].text == callout
    assert callout_entries[0].metadata["callout_type"] == "note"
    assert len(definition_entries) == 1
    assert definition_entries[0].text == definition
    structured = table_entries + callout_entries + definition_entries
    assert all(
        "structure_type" not in e.metadata
        for e in entries
        if e not in structured
    )


def test_adaptive_sizing_through_pipeline(tmp_settings: Settings) -> None:
    """P3-205: heading_depth-driven chunk budgets flow from settings through
    ``IngestionWorkflow.create_default`` into the stored entries — a ``###``
    section yields more, smaller chunks than the same body under ``#``."""
    tmp_settings.chunking.sentence_tokenizer = "heuristic"
    tmp_settings.chunking.heading_size_step = 1000
    tmp_settings.chunking.min_chunk_chars = 200
    workflow = IngestionWorkflow.create_default(tmp_settings)
    workflow._embedding_service = FakeEmbeddingService()
    body = "A full sentence describing a knowledge base feature with many words. " * 120
    _, stored, _ = workflow._run_knowledge_engine(
        _document(
            "adaptive.md",
            "# Top Section\n\n" + body + "\n\n### Deep Section\n\n" + body,
        ),
        _analysis("Doc", "Concept"),
    )
    entries = list(workflow._vector_store._entries.values())
    assert stored == len(entries)
    top = [e for e in entries if e.metadata.get("heading") == "Top Section"
           and not e.text.startswith("#")]
    deep = [e for e in entries if e.metadata.get("heading") == "Deep Section"
            and not e.text.startswith("#")]
    assert len(deep) > len(top)
    assert max(len(e.text) for e in deep) < min(len(e.text) for e in top)


def test_heading_overlap_boundary_through_pipeline(tmp_settings: Settings) -> None:
    """P3-205: with ``heading_overlap_boundary`` the stored entry that opens a
    new section starts at its heading — no previous-section tail is prepended."""
    tmp_settings.chunking.sentence_tokenizer = "heuristic"
    workflow = IngestionWorkflow.create_default(tmp_settings)
    workflow._embedding_service = FakeEmbeddingService()
    body = "A full sentence describing a knowledge base feature with many words. " * 40
    text = "# First\n\n" + body + "\n\n## Second\n\n" + body

    workflow._chunker = SemanticChunker(policy=ChunkingPolicy(heading_overlap_boundary=True))
    _, stored, _ = workflow._run_knowledge_engine(
        _document("boundary.md", text), _analysis("Doc", "Concept")
    )
    blocked = {
        e.text for e in list(workflow._vector_store._entries.values())
        if e.metadata.get("heading") == "Second"
    }
    assert stored >= 2
    assert len(blocked) >= 2
    # the heading-led chunk of the section is emitted as-is: no prepended tail
    assert "## Second" in blocked
    assert any(e.startswith("## Second") for e in blocked)

    workflow._chunker = SemanticChunker()
    _, _, _ = workflow._run_knowledge_engine(
        _document("boundary.md", text), _analysis("Doc", "Concept")
    )
    plain = {
        e.text for e in list(workflow._vector_store._entries.values())
        if e.metadata.get("heading") == "Second"
    }
    # P3-204 default: the heading fragment carries a prepended tail
    assert "## Second" not in plain
    assert any(e.startswith("## Second") for e in plain)
