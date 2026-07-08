"""Integration tests for the complete ingestion workflow."""

from __future__ import annotations

from typing import Any

from app.application import AIProcessingResult
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow
from app.templates import ObsidianMarkdownGenerator


class FakeDocumentProcessor:
    """Fake processor used to test the full workflow without a live Ollama server."""

    def process(self, document: SourceDocument) -> AIProcessingResult:
        return AIProcessingResult(
            document=document,
            analysis=_analysis(),
            attempts=1,
        )


def test_complete_workflow_from_markdown_to_obsidian_vault(tmp_path) -> None:
    source_path = tmp_path / "input.md"
    vault_path = tmp_path / "vault"
    source_path.write_text(
        """
# Local   Memory

This     document explains a local AI memory system.

-   Ingest documents
-   Generate notes

```python
value    = "keep spacing"
```
""",
        encoding="utf-8",
    )

    workflow = IngestionWorkflow(
        ingestion_service=DocumentIngestionService(),
        processor=FakeDocumentProcessor(),
        note_generator=ObsidianMarkdownGenerator(),
        writer=VaultWriter(vault_path),
    )

    result = workflow.run(source_path, expected_source_type="markdown")

    assert result.document.text.startswith("# Local Memory")
    assert 'value    = "keep spacing"' in result.document.text
    assert result.note.title == "Local AI Memory"
    assert result.write_result.created is True
    assert result.write_result.note_path == vault_path / "Notes" / "Local AI Memory.md"
    assert result.write_result.note_path.exists()
    assert (vault_path / "index.md").exists()
    assert (vault_path / "overview.md").exists()
    assert (vault_path / "log.md").exists()

    note_text = result.write_result.note_path.read_text(encoding="utf-8")
    assert "[[Local AI memory]]" in note_text
    assert "## Wiki Navigation" in note_text
    assert "[[index]]" in note_text


def test_complete_workflow_updates_existing_note_without_user_content_loss(tmp_path) -> None:
    source_path = tmp_path / "input.md"
    vault_path = tmp_path / "vault"
    source_path.write_text("# Local Memory\n\nOriginal text.", encoding="utf-8")

    workflow = IngestionWorkflow(
        ingestion_service=DocumentIngestionService(),
        processor=FakeDocumentProcessor(),
        note_generator=ObsidianMarkdownGenerator(),
        writer=VaultWriter(vault_path),
    )

    first = workflow.run(source_path, expected_source_type="markdown")
    with first.write_result.note_path.open("a", encoding="utf-8") as handle:
        handle.write("\n## Human Notes\n\nKeep this paragraph.\n")

    source_path.write_text("# Local Memory\n\nChanged text.", encoding="utf-8")
    second = workflow.run(source_path, expected_source_type="markdown")

    assert second.write_result.created is False
    assert second.write_result.updated is True
    note_text = second.write_result.note_path.read_text(encoding="utf-8")
    assert "Keep this paragraph." in note_text
    assert note_text.count("<!-- PAM:BEGIN MANAGED -->") == 1


def _analysis() -> DocumentAnalysis:
    payload: dict[str, Any] = {
        "suggested_note_title": "Local AI Memory",
        "summary": {
            "short": "A local AI memory system.",
            "detailed": "The source explains a local AI memory system for durable notes.",
        },
        "key_concepts": [
            {
                "name": "Local AI memory",
                "explanation": "A local system for building durable personal knowledge.",
                "importance": "high",
            }
        ],
        "definitions": [
            {
                "term": "Incremental ingestion",
                "definition": "Adding changed sources without rebuilding the whole wiki.",
            }
        ],
        "important_entities": [
            {
                "name": "Obsidian",
                "type": "product",
                "description": "A Markdown knowledge base application.",
            }
        ],
        "tags": ["local-ai", "memory"],
        "related_topics": [
            {
                "topic": "Personal knowledge management",
                "reason": "The source is about maintaining useful personal knowledge.",
            }
        ],
    }
    return DocumentAnalysis.model_validate(payload)
