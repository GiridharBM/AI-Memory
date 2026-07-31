"""Live Ollama pipeline smoke test.

Requires a running Ollama server with ``llama3.1:8b`` pulled. Skipped by
default; run explicitly with::

    python -m pytest tests/integration/smoke_test.py -m integration -s
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import OllamaSettings
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.llm import OllamaClient
from app.infrastructure.llm.ollama_client import OllamaRequest
from app.prompts.document_analysis import DOCUMENT_ANALYSIS_SYSTEM_PROMPT
from app.templates.obsidian_note import ObsidianMarkdownGenerator

_REQUIRED_SECTIONS = [
    "## Summary", "## Table of Contents", "## Reading Time", "## Difficulty Level",
    "## Keywords", "## Categories", "## Key Concepts", "## Definitions",
    "## Important Entities", "## Related Topics", "## Suggested Related Notes",
    "## Suggested Backlinks", "## Frequently Asked Questions", "## Flashcards",
    "## Multiple Choice Questions", "## Short Answer Questions", "## Long Answer Questions",
    "## Revision Notes", "## Tags", "## Metadata", "## References",
]

_CODE = (
    "def fibonacci(n):\n"
    "    if n <= 1:\n"
    "        return n\n"
    "    return fibonacci(n-1) + fibonacci(n-2)\n"
    "\n"
    "# Classic recursive fibonacci implementation"
)


@pytest.mark.integration
def test_live_ollama_analysis_and_note_generation(tmp_path: Path) -> None:
    client = OllamaClient(OllamaSettings(timeout_seconds=300))
    doc = SourceDocument(
        source="test.py",
        source_path=Path("test.py"),
        source_type="code",
        filename="test.py",
        text=_CODE,
        metadata=DocumentMetadata(title="Fibonacci"),
    )

    prompt = f"""Analyze this source for a personal Obsidian knowledge base.
Return only the structured JSON requested by the system prompt.

Source metadata:
- Source type: {doc.source_type}
- Filename: {doc.filename}
- Existing title: {doc.metadata.title}

Source text:
\"\"\"
{doc.text}
\"\"\"
"""

    request = OllamaRequest(
        system_prompt=DOCUMENT_ANALYSIS_SYSTEM_PROMPT,
        prompt=prompt,
        model="llama3.1:8b",
    )
    analysis = client.generate_json(request, response_model=DocumentAnalysis)

    note = ObsidianMarkdownGenerator().generate(
        document=doc, analysis=analysis, processing_confidence=0.92,
    )

    missing = [s for s in _REQUIRED_SECTIONS if s not in note.markdown]
    assert not missing, f"Missing sections: {missing}"

    out = tmp_path / "sample_note.md"
    out.write_text(note.markdown, encoding="utf-8")
    assert out.read_text(encoding="utf-8") == note.markdown
