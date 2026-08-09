"""Tests for the built-in metadata extractors (P2-202)."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.metadata import MetadataExtractor
from app.infrastructure.document_intelligence.metadata.extractors import (
    DEFAULT_EXTRACTORS,
    AudioExtractor,
    DocxExtractor,
    EmailExtractor,
    NotebookExtractor,
    PdfExtractor,
    PptxExtractor,
)
from app.infrastructure.ingestion.pdf_ingestor import PdfIngestor

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

_CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/">
  <dc:title>Quarterly Report</dc:title>
  <dc:creator>Alice</dc:creator>
  <dcterms:created>2024-03-01T10:00:00Z</dcterms:created>
  <dcterms:modified>2024-03-15T14:30:00Z</dcterms:modified>
  <cp:lastModifiedBy>Bob</cp:lastModifiedBy>
</cp:coreProperties>"""


def _write_ooxml(path: Path, app_xml: str) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("docProps/core.xml", _CORE_XML)
        zf.writestr("docProps/app.xml", app_xml)


def _source_document(path: Path, source_type: str) -> SourceDocument:
    return SourceDocument(
        source=str(path),
        source_path=path,
        source_type=source_type,
        filename=path.name,
        text="",
        metadata=DocumentMetadata(),
    )


def test_all_builtins_implement_protocol():
    assert all(isinstance(e, MetadataExtractor) for e in DEFAULT_EXTRACTORS)


def test_default_extractors_cover_all_six_source_types():
    covered = {t for e in DEFAULT_EXTRACTORS for t in e.source_types}
    assert covered == {"pdf", "docx", "pptx", "notebook", "audio", "email"}


def test_pdf_extractor_output_equals_pdf_ingestor_metadata(tmp_path: Path):
    import fitz

    pdf_path = tmp_path / "report.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Real extractable content")
    doc.set_metadata(
        {
            "title": "Frozen Spec",
            "author": "Jane Doe",
            "creationDate": "D:20240101120000+00'00'",
            "producer": "PyMuPDF",
            "subject": "Milestone 2.2",
        }
    )
    doc.save(str(pdf_path))
    doc.close()

    ingested = PdfIngestor().ingest(pdf_path)
    values = PdfExtractor().extract(ingested)

    assert ingested.source_type == "pdf"
    assert values["title"] == ingested.metadata.title
    assert values["author"] == ingested.metadata.author
    assert values["created_at"] == ingested.metadata.created_at
    assert values["modified_at"] == ingested.metadata.modified_at
    assert values["page_count"] == ingested.metadata.page_count == 1
    assert values["mime_type"] == ingested.metadata.mime_type == "application/pdf"
    assert values["producer"] == ingested.metadata.extra["producer"]
    assert values["subject"] == ingested.metadata.extra["subject"]
    assert values["created_at"] == datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


def test_pdf_extractor_falls_back_to_stem_when_no_title(tmp_path: Path):
    import fitz

    pdf_path = tmp_path / "untitled.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Some text")
    doc.save(str(pdf_path))
    doc.close()

    values = PdfExtractor().extract(_source_document(pdf_path, "pdf"))

    assert values["title"] == "untitled"
    assert values["mime_type"] == "application/pdf"
    assert values["page_count"] == 1


def test_pdf_extractor_never_raises_on_corrupt_file(tmp_path: Path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-not-a-real-file")

    assert PdfExtractor().extract(_source_document(path, "pdf")) == {}


def test_docx_extractor_reads_core_properties(tmp_path: Path):
    path = tmp_path / "quarterly.docx"
    _write_ooxml(
        path,
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Pages>12</Pages>
</Properties>""",
    )

    values = DocxExtractor().extract(_source_document(path, "docx"))

    assert values["title"] == "Quarterly Report"
    assert values["author"] == "Alice"
    assert values["last_modified_by"] == "Bob"
    assert values["created_at"] == datetime(2024, 3, 1, 10, 0, tzinfo=UTC)
    assert values["modified_at"] == datetime(2024, 3, 15, 14, 30, tzinfo=UTC)
    assert values["page_count"] == 12
    assert values["mime_type"] == _DOCX_MIME


def test_pptx_extractor_reads_slides_count(tmp_path: Path):
    path = tmp_path / "deck.pptx"
    _write_ooxml(
        path,
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Slides>5</Slides>
</Properties>""",
    )

    values = PptxExtractor().extract(_source_document(path, "pptx"))

    assert values["title"] == "Quarterly Report"
    assert values["author"] == "Alice"
    assert values["page_count"] == 5
    assert values["mime_type"] == _PPTX_MIME


def test_ooxml_extractor_falls_back_on_non_zip(tmp_path: Path):
    path = tmp_path / "corrupt.docx"
    path.write_bytes(b"not a zip archive")

    values = DocxExtractor().extract(_source_document(path, "docx"))

    assert values["title"] == "corrupt"
    assert values["modified_at"] is not None
    assert values["mime_type"] == _DOCX_MIME
    assert "author" not in values


def test_notebook_extractor_reads_kernelspec(tmp_path: Path):
    path = tmp_path / "analysis.ipynb"
    path.write_text(
        json.dumps(
            {
                "cells": [{"cell_type": "code", "source": ["print(1)"]}],
                "metadata": {
                    "kernelspec": {"display_name": "Python 3", "language": "python"},
                },
            }
        ),
        encoding="utf-8",
    )

    values = NotebookExtractor().extract(_source_document(path, "notebook"))

    assert values["title"] == "analysis"
    assert values["cell_count"] == 1
    assert values["kernel"] == "Python 3"
    assert values["language"] == "python"
    assert values["mime_type"] == "application/x-ipynb+json"
    assert values["modified_at"] is not None


def test_notebook_extractor_never_raises_on_invalid_json(tmp_path: Path):
    path = tmp_path / "broken.ipynb"
    path.write_text("{not valid json", encoding="utf-8")

    assert NotebookExtractor().extract(_source_document(path, "notebook")) == {}


def test_audio_extractor_deterministic_file_fields(tmp_path: Path):
    path = tmp_path / "podcast.mp3"
    path.write_bytes(b"\xff\xfb" + b"\x00" * 16)

    values = AudioExtractor().extract(_source_document(path, "audio"))

    assert values["title"] == "podcast"
    assert values["mime_type"] == "audio/mpeg"
    assert values["modified_at"] is not None


def test_audio_extractor_unknown_extension_mime(tmp_path: Path):
    path = tmp_path / "clip.wav"
    path.write_bytes(b"\x00")

    values = AudioExtractor().extract(_source_document(path, "audio"))

    assert values["mime_type"] == "audio/wav"


def test_email_extractor_reads_headers(tmp_path: Path):
    path = tmp_path / "message.eml"
    path.write_text(
        "From: sender@example.com\n"
        "To: recipient@example.com\n"
        "Date: Mon, 21 Jul 2026 10:00:00 +0000\n"
        "Subject: Test Email\n"
        "\n"
        "Body text.",
        encoding="utf-8",
    )

    values = EmailExtractor().extract(_source_document(path, "email"))

    assert values["title"] == "Test Email"
    assert values["subject"] == "Test Email"
    assert values["from"] == "sender@example.com"
    assert values["to"] == "recipient@example.com"
    assert "Test Email" not in values["to"]
    assert values["mime_type"] == "message/rfc822"


def test_email_extractor_never_raises_on_binary_garbage(tmp_path: Path):
    path = tmp_path / "garbage.eml"
    path.write_bytes(b"\x00\x01\x02")

    values = EmailExtractor().extract(_source_document(path, "email"))

    assert values["mime_type"] == "message/rfc822"
    assert values["title"] == ""
