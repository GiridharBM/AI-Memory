"""Integration tests for P2-208 email attachment recursive ingestion (M2.2).

The frozen Acceptance Criterion (spec §P2-208, R-1 / Epic 2 AC 6): an RFC822
email with 3 PDF attachments produces 1 parent note + 3 child notes with
``parent_id`` set. Unit-level coverage for the cap, size-limit, and depth-guard
behavior lives in ``tests/unit/test_email_attachments.py``.

The ``test_create_default_*`` tests are the R1 regression net: they build the
workflow through the production wiring (``IngestionWorkflow.create_default``)
and verify that ``intelligence.metadata.{email_attachments,max_file_size_mb,
max_attachments}`` actually reach the ingestion service (which is what R1
required).
"""

from __future__ import annotations

import hashlib
import tempfile
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest

from app.application import AIProcessingResult
from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.infrastructure.ingestion.service import DocumentIngestionService
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow
from app.templates import ObsidianMarkdownGenerator


class RecordingProcessor:
    """Fake AI processor that records every document it is handed."""

    def __init__(self) -> None:
        self.documents: list[SourceDocument] = []

    def process(self, document: SourceDocument) -> AIProcessingResult:
        self.documents.append(document)
        return AIProcessingResult(
            document=document, analysis=_analysis(document.text), attempts=1,
        )


def _write_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), f"PDF content {path.stem}")
    doc.save(str(path))
    doc.close()


@pytest.mark.integration
def test_email_with_three_pdf_attachments_produces_four_notes(tmp_path: Path) -> None:
    eml = tmp_path / "bundle.eml"
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 21 Jul 2026 10:00:00 +0000"
    msg["Subject"] = "Bundle"
    msg.set_content("Attached three PDFs.")
    for name in ("one.pdf", "two.pdf", "three.pdf"):
        pdf = tmp_path / name
        _write_pdf(pdf)
        msg.add_attachment(
            pdf.read_bytes(), maintype="application", subtype="pdf", filename=name,
        )
    eml.write_bytes(msg.as_bytes())

    processor = RecordingProcessor()
    vault = tmp_path / "vault"
    workflow = IngestionWorkflow(
        ingestion_service=DocumentIngestionService(),
        processor=processor,
        note_generator=ObsidianMarkdownGenerator(),
        writer=VaultWriter(vault),
    )

    result = workflow.run(eml, expected_source_type="email")

    assert result.document.source_type == "email"
    assert len(processor.documents) == 4
    parent_id = str(eml.expanduser().resolve())
    assert processor.documents[0].source_type == "email"
    assert "parent_id" not in processor.documents[0].metadata.extra
    for child in processor.documents[1:]:
        assert child.source_type == "pdf"
        assert child.metadata.extra["parent_id"] == parent_id
    assert len(list((vault / "Notes").glob("*.md"))) == 4
    for path_str in result.document.metadata.extra["attachment_paths"]:
        assert not Path(path_str).exists()


def _write_eml(
    path: Path,
    *,
    attachments: tuple[tuple[str, bytes], ...] = (),
) -> Path:
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 21 Jul 2026 10:00:00 +0000"
    msg["Subject"] = "Test Email"
    msg.set_content("Body text.")
    for filename, payload in attachments:
        if filename.endswith(".txt"):
            maintype, subtype = "text", "plain"
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)
    path.write_bytes(msg.as_bytes())
    return path


def _production_workflow(settings: Settings) -> IngestionWorkflow:
    """Build via ``create_default`` (production wiring) with network steps off."""
    workflow = IngestionWorkflow.create_default(settings)
    workflow._processor = RecordingProcessor()
    workflow._chunker = None
    workflow._embedding_service = None
    workflow._vector_store = None
    workflow._kg_builder = None
    workflow._graph_path = None
    return workflow


def _temp_attachment_dirs() -> set[Path]:
    return set(Path(tempfile.gettempdir()).glob("pam_email_attachments_*"))


def test_create_default_wires_metadata_settings_to_service(tmp_settings: Settings) -> None:
    tmp_settings.intelligence.metadata.email_attachments = False
    tmp_settings.intelligence.metadata.max_file_size_mb = 7
    tmp_settings.intelligence.metadata.max_attachments = 3

    workflow = IngestionWorkflow.create_default(tmp_settings)
    service_metadata = workflow._ingestion_service._metadata()

    assert service_metadata.email_attachments is False
    assert service_metadata.max_file_size_mb == 7
    assert service_metadata.max_attachments == 3


def test_create_default_email_attachments_false_extracts_nothing(
    tmp_settings: Settings, tmp_path: Path,
) -> None:
    tmp_settings.intelligence.metadata.email_attachments = False
    eml = _write_eml(tmp_path / "mail.eml", attachments=(("a.txt", b"alpha content"),))
    workflow = _production_workflow(tmp_settings)

    before = _temp_attachment_dirs()
    workflow.run(eml, expected_source_type="email")

    assert len(workflow._processor.documents) == 1
    assert _temp_attachment_dirs() == before


def test_create_default_enforces_max_file_size_mb(tmp_settings: Settings, tmp_path: Path) -> None:
    tmp_settings.intelligence.metadata.max_file_size_mb = 1
    workflow = IngestionWorkflow.create_default(tmp_settings)
    big = tmp_path / "big.md"
    big.write_bytes(b"x" * (1024 * 1024 + 1))

    result = workflow._ingestion_service.ingest(big)

    assert not result.succeeded
    assert result.error is not None
    assert "size limit" in result.error.reason


def test_create_default_honors_max_attachments(tmp_settings: Settings, tmp_path: Path) -> None:
    tmp_settings.intelligence.metadata.max_attachments = 1
    eml = _write_eml(
        tmp_path / "mail.eml",
        attachments=(("a.txt", b"alpha content"), ("b.txt", b"beta content")),
    )
    workflow = _production_workflow(tmp_settings)

    before = _temp_attachment_dirs()
    workflow.run(eml, expected_source_type="email")

    assert len(workflow._processor.documents) == 2
    assert {d.text for d in workflow._processor.documents[1:]} == {"alpha content"}
    assert _temp_attachment_dirs() == before


def _analysis(text: str) -> DocumentAnalysis:
    title = "Note-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    payload: dict[str, Any] = {
        "suggested_note_title": title,
        "summary": {"short": "A short summary.", "detailed": "A detailed summary."},
        "key_concepts": [
            {"name": "Concept", "explanation": "An explanation.", "importance": "high"}
        ],
        "definitions": [{"term": "Term", "definition": "A definition."}],
        "important_entities": [
            {"name": "Entity", "type": "other", "description": "A description."}
        ],
        "tags": ["test"],
        "related_topics": [{"topic": "Topic", "reason": "A reason."}],
    }
    return DocumentAnalysis.model_validate(payload)
