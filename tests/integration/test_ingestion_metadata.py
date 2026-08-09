"""Integration tests for P2-207 metadata enrichment wiring (M2.2)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.core.config import IntelligenceSettings, MetadataSettings, Settings, load_settings
from app.domain.documents import SourceDocument
from app.infrastructure.document_intelligence.metadata import DocumentMetadataService
from app.infrastructure.ingestion.docx_ingestor import DocxIngestor
from app.infrastructure.ingestion.email_ingestor import EmailIngestor
from app.infrastructure.ingestion.notebook_ingestor import NotebookIngestor
from app.infrastructure.ingestion.pdf_ingestor import PdfIngestor
from app.infrastructure.ingestion.service import DocumentIngestionService
from app.infrastructure.ingestion.txt_ingestor import TextIngestor

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _disabled_settings() -> Settings:
    base = load_settings()
    return base.model_copy(
        update={"intelligence": IntelligenceSettings(metadata=MetadataSettings(enabled=False))}
    )


def _write_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Enrichment integration content")
    doc.set_metadata(
        {
            "title": "Integration Report",
            "author": "Jane Doe",
            "creationDate": "D:20240101120000+00'00'",
            "producer": "PyMuPDF",
            "subject": "M2.2",
        }
    )
    doc.save(str(path))
    doc.close()


def _write_docx(path: Path) -> None:
    from docx import Document

    draft = path.with_suffix(".draft.docx")
    doc = Document()
    doc.add_paragraph("Enrichment docx body")
    doc.core_properties.title = "Quarterly Report"
    doc.core_properties.author = "Alice"
    doc.save(str(draft))

    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        "<Pages>7</Pages></Properties>"
    )
    with zipfile.ZipFile(draft, "r") as src, zipfile.ZipFile(path, "w") as dst:
        for info in src.infolist():
            if info.filename == "docProps/app.xml":
                continue
            dst.writestr(info, src.read(info.filename))
        dst.writestr("docProps/app.xml", app_xml)
    draft.unlink()


def _write_notebook(path: Path) -> None:
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


def _write_email(path: Path) -> None:
    path.write_text(
        "From: sender@example.com\n"
        "To: recipient@example.com\n"
        "Date: Mon, 21 Jul 2026 10:00:00 +0000\n"
        "Subject: Test Email\n"
        "\n"
        "Body text.",
        encoding="utf-8",
    )


@pytest.mark.integration
def test_pdf_ingest_enriches_metadata_superset(tmp_path: Path) -> None:
    path = tmp_path / "report.pdf"
    _write_pdf(path)

    enabled = DocumentIngestionService().ingest(path)
    disabled = DocumentIngestionService(settings=_disabled_settings()).ingest(path)

    assert enabled.succeeded and disabled.succeeded
    phase1 = PdfIngestor().ingest(path)
    assert disabled.document is not None
    assert disabled.document.metadata == phase1.metadata
    assert disabled.document.text == phase1.text

    assert enabled.document is not None
    enriched = enabled.document.metadata
    assert enriched.title == "Integration Report"
    assert enriched.author == "Jane Doe"
    assert enriched.page_count == 1
    assert enriched.mime_type == "application/pdf"
    assert enriched.extra["subject"] == "M2.2"


@pytest.mark.integration
def test_docx_ingest_enriches_metadata_superset(tmp_path: Path) -> None:
    pytest.importorskip("docx")
    path = tmp_path / "quarterly.docx"
    _write_docx(path)

    enabled = DocumentIngestionService().ingest(path)
    disabled = DocumentIngestionService(settings=_disabled_settings()).ingest(path)

    assert enabled.succeeded and disabled.succeeded
    phase1 = DocxIngestor().ingest(path)
    assert disabled.document is not None
    assert disabled.document.metadata == phase1.metadata

    assert enabled.document is not None
    enriched = enabled.document.metadata
    assert enriched.title == "Quarterly Report"
    assert enriched.author == "Alice"
    assert enriched.mime_type == _DOCX_MIME


@pytest.mark.integration
def test_notebook_ingest_enriches_metadata_superset(tmp_path: Path) -> None:
    path = tmp_path / "analysis.ipynb"
    _write_notebook(path)

    enabled = DocumentIngestionService().ingest(path)
    disabled = DocumentIngestionService(settings=_disabled_settings()).ingest(path)

    assert enabled.succeeded and disabled.succeeded
    phase1 = NotebookIngestor().ingest(path)
    assert disabled.document is not None
    assert disabled.document.metadata == phase1.metadata

    assert enabled.document is not None
    enriched = enabled.document.metadata
    assert enriched.title == "analysis"
    assert enriched.mime_type == "application/x-ipynb+json"
    assert enriched.extra["cell_count"] == 1
    assert enriched.extra["kernel"] == "Python 3"
    assert enriched.extra["language"] == "python"


@pytest.mark.integration
def test_email_ingest_enriches_metadata_superset(tmp_path: Path) -> None:
    path = tmp_path / "message.eml"
    _write_email(path)

    enabled = DocumentIngestionService().ingest(path)
    disabled = DocumentIngestionService(settings=_disabled_settings()).ingest(path)

    assert enabled.succeeded and disabled.succeeded
    phase1 = EmailIngestor().ingest(path)
    assert disabled.document is not None
    assert disabled.document.metadata == phase1.metadata

    assert enabled.document is not None
    enriched = enabled.document.metadata
    assert enriched.title == "Test Email"
    assert enriched.mime_type == "message/rfc822"
    assert enriched.extra["subject"] == "Test Email"
    assert enriched.extra["from"] == "sender@example.com"


class _RaisingExtractor:
    name = "raising"
    source_types = ("text",)

    def extract(self, document: SourceDocument) -> dict[str, object]:
        raise RuntimeError("boom")


@pytest.mark.integration
def test_extractor_failure_leaves_document_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("unchanged text", encoding="utf-8")

    service = DocumentIngestionService(
        metadata_service=DocumentMetadataService([_RaisingExtractor()])
    )
    result = service.ingest(path)

    assert result.succeeded
    baseline = TextIngestor().ingest(path)
    assert result.document is not None
    assert result.document.metadata == baseline.metadata
    assert result.document.text == baseline.text
