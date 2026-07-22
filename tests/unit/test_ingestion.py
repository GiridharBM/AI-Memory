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
    path = tmp_path / "data.xyz"
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


# ── New ingestor tests ─────────────────────────────────────────────────────


def test_ingests_notebook_file(tmp_path: Path) -> None:
    path = tmp_path / "analysis.ipynb"
    notebook = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Analysis\n", "This is a notebook."]},
            {"cell_type": "code", "source": ["print('hello')"]},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3"}},
    }
    import json
    path.write_text(json.dumps(notebook), encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "notebook"
    assert "Analysis" in result.document.text
    assert "print('hello')" in result.document.text


def test_ingests_email_eml_file(tmp_path: Path) -> None:
    path = tmp_path / "message.eml"
    content = (
        "From: sender@example.com\n"
        "To: recipient@example.com\n"
        "Date: Mon, 21 Jul 2026 10:00:00 +0000\n"
        "Subject: Test Email\n"
        "\n"
        "This is the email body."
    )
    path.write_text(content, encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "email"
    assert "sender@example.com" in result.document.text
    assert "Test Email" in result.document.text
    assert "email body" in result.document.text


def test_ingests_database_sqlite_file(tmp_path: Path) -> None:
    import sqlite3
    path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO users VALUES (1, 'Alice')")
    cursor.execute("INSERT INTO users VALUES (2, 'Bob')")
    conn.commit()
    conn.close()

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "database"
    assert "users" in result.document.text
    assert "Alice" in result.document.text


def test_ingests_research_bib_file(tmp_path: Path) -> None:
    path = tmp_path / "refs.bib"
    content = (
        "@article{smith2024,\n"
        "  title = {Deep Learning Survey},\n"
        "  author = {Smith, John},\n"
        "  year = {2024}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "research"
    assert "Deep Learning Survey" in result.document.text


def test_ingests_research_ris_file(tmp_path: Path) -> None:
    path = tmp_path / "refs.ris"
    content = (
        "TI  - Deep Learning Survey\n"
        "AU  - Smith, John\n"
        "PY  - 2024\n"
        "ER  - \n"
    )
    path.write_text(content, encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "research"
    assert "Deep Learning Survey" in result.document.text


def test_ingests_archive_zip_file(tmp_path: Path) -> None:
    import zipfile
    path = tmp_path / "archive.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("file1.txt", "content1")
        zf.writestr("file2.txt", "content2")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "archive"
    assert "file1.txt" in result.document.text
    assert "file2.txt" in result.document.text


def test_ingests_diagram_drawio_file(tmp_path: Path) -> None:
    path = tmp_path / "arch.drawio"
    content = (
        '<mxfile>\n'
        '  <diagram>\n'
        '    <mxGraphModel>\n'
        '      <root>\n'
        '        <mxCell value="Server" />\n'
        '        <mxCell value="Database" />\n'
        '      </root>\n'
        '    </mxGraphModel>\n'
        '  </diagram>\n'
        '</mxfile>'
    )
    path.write_text(content, encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "diagram"
    assert "Server" in result.document.text
    assert "Database" in result.document.text


def test_ingests_csv_file(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("name,age\nAlice,30\nBob,25", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "csv"
    assert "Alice" in result.document.text


def test_ingests_tsv_file(tmp_path: Path) -> None:
    path = tmp_path / "data.tsv"
    path.write_text("name\tage\nAlice\t30\nBob\t25", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "csv"
    assert "Alice" in result.document.text


def test_ingests_html_file(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text("<html><body><h1>Test</h1><p>Hello world</p></body></html>", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "text"
    assert "Hello world" in result.document.text


def test_ingests_json_file(tmp_path: Path) -> None:
    import json
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"key": "value"}), encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "text"
    assert "key" in result.document.text


def test_ingests_xml_file(tmp_path: Path) -> None:
    path = tmp_path / "data.xml"
    path.write_text("<root><item>Test</item></root>", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "text"
    assert "Test" in result.document.text


def test_ingests_css_file(tmp_path: Path) -> None:
    path = tmp_path / "style.css"
    path.write_text("body { color: red; }", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "code"
    assert "color: red" in result.document.text


def test_ingests_toml_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[app]\nname = "test"', encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "config"
    assert "test" in result.document.text


def test_ingests_python_file(tmp_path: Path) -> None:
    path = tmp_path / "script.py"
    path.write_text("def hello():\n    print('hello')", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "code"
    assert "hello" in result.document.text


def test_ingests_typescript_file(tmp_path: Path) -> None:
    path = tmp_path / "app.ts"
    path.write_text("const x: number = 42;", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "code"
    assert "42" in result.document.text


def test_ingests_kotlin_file(tmp_path: Path) -> None:
    path = tmp_path / "Main.kt"
    path.write_text("fun main() { println(\"hello\") }", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "code"
    assert "hello" in result.document.text


def test_ingests_swift_file(tmp_path: Path) -> None:
    path = tmp_path / "App.swift"
    path.write_text("print(\"hello\")", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "code"


def test_ingests_sql_file(tmp_path: Path) -> None:
    path = tmp_path / "query.sql"
    path.write_text("SELECT * FROM users WHERE id = 1;", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "code"
    assert "SELECT" in result.document.text


def test_ingests_tex_file(tmp_path: Path) -> None:
    path = tmp_path / "paper.tex"
    content = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Hello world\n"
        "\\end{document}"
    )
    path.write_text(content, encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "text"
    assert "Hello world" in result.document.text


def test_ingests_env_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("API_KEY=secret123\nDEBUG=true", encoding="utf-8")

    result = DocumentIngestionService().ingest(path)

    assert result.succeeded
    assert result.document is not None
    assert result.document.source_type == "config"
    assert "secret123" in result.document.text


def test_supported_extensions_includes_new_types() -> None:
    service = DocumentIngestionService()
    extensions = service.supported_extensions()

    assert ".ipynb" in extensions
    assert ".eml" in extensions
    assert ".sqlite" in extensions
    assert ".bib" in extensions
    assert ".zip" in extensions
    assert ".drawio" in extensions
    assert ".tsv" in extensions
    assert ".jsx" in extensions
    assert ".kt" in extensions
    assert ".swift" in extensions
    assert ".heic" in extensions
    assert ".aac" in extensions
    assert ".odt" in extensions
    assert ".rtf" in extensions
    assert ".epub" in extensions
    assert ".tex" in extensions
    assert ".css" in extensions
    assert ".toml" in extensions
