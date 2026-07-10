"""Tests for source ingestion adapters."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.ingestion.github_readme_ingestor import GitHubReadmeIngestor
from app.infrastructure.ingestion.pdf_ingestor import PdfIngestor
from app.infrastructure.ingestion.youtube_transcript_ingestor import YouTubeTranscriptIngestor


def test_ingests_markdown_file(tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text("# Title\n\nText     with     spaces.", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "markdown"
    assert result.document.metadata.title == "Title"
    assert result.document.text == "# Title\n\nText with spaces."


def test_ingests_txt_file(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("Text     with     spaces.", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "text"
    assert result.document.text == "Text with spaces."


def test_unsupported_file_returns_structured_error(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("a,b", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert not result.succeeded
    assert result.error is not None
    assert "Unsupported source" in result.error.reason


def test_pdf_ingestor_extracts_text_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF fake")

    class FakeReader:
        metadata = {"/Title": "Paper Title", "/Author": "Ada", "/CreationDate": "D:20260708123000"}
        pages = [SimpleNamespace(extract_text=lambda: "Page     text")]

    monkeypatch.setattr(
        "app.infrastructure.ingestion.pdf_ingestor.PdfReader",
        lambda _: FakeReader(),
    )

    document = PdfIngestor().ingest(path)

    assert document.source_type == "pdf"
    assert document.metadata.title == "Paper Title"
    assert document.metadata.author == "Ada"
    assert document.metadata.page_count == 1
    assert document.text == "Page text"


def test_github_readme_ingestor_downloads_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(url: str) -> dict[str, object]:
        if url.endswith("/readme"):
            return {
                "name": "README.md",
                "path": "README.md",
                "content": "IyBUaXRsZQoKVGV4dCAgICAgd2l0aCBzcGFjZXMu",
            }
        return {
            "full_name": "owner/repo",
            "owner": {"login": "owner"},
            "updated_at": "2026-07-08T12:30:00Z",
            "default_branch": "main",
            "description": "Demo repo",
        }

    monkeypatch.setattr(
        "app.infrastructure.ingestion.github_readme_ingestor._fetch_json",
        fake_fetch,
    )

    document = GitHubReadmeIngestor().ingest("https://github.com/owner/repo")

    assert document.source_type == "github_readme"
    assert document.filename == "README.md"
    assert document.metadata.title == "owner/repo"
    assert document.text == "# Title\n\nText with spaces."


def test_youtube_ingestor_handles_missing_transcript() -> None:
    result = DocumentIngestionService().ingest("https://www.youtube.com/watch?v=abc123")

    assert not result.succeeded
    assert result.error is not None
    assert result.error.source_type == "youtube_transcript"


def test_youtube_ingestor_downloads_transcript() -> None:
    class FakeTranscript:
        language = "English"
        language_code = "en"
        is_generated = False
        video_id = "abc123"

        def to_raw_data(self) -> list[dict[str, str]]:
            return [{"text": "Hello    world"}, {"text": "Second line"}]

    class FakeClient:
        def fetch(self, video_id: str, languages: list[str]) -> FakeTranscript:
            assert video_id == "abc123"
            assert "en" in languages
            return FakeTranscript()

    ingestor = YouTubeTranscriptIngestor()
    ingestor._client = cast(Any, FakeClient())

    document = ingestor.ingest("https://www.youtube.com/watch?v=abc123")

    assert document.source_type == "youtube_transcript"
    assert document.filename == "abc123.transcript.md"
    assert document.text == "Hello world\nSecond line"
