"""Unit tests for P2-208 recursive email-attachment ingestion (M2.2).

Covers attachment extraction in ``EmailIngestor`` and the workflow-level
parent/child re-ingestion (``parent_id`` stamping, ``max_attachments`` cap,
size-limit reuse via the shared ``DocumentIngestionService``, one-level depth
guard, and temp-file cleanup).
"""

from __future__ import annotations

import hashlib
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from app.application import AIProcessingResult
from app.core.config import IntelligenceSettings, MetadataSettings, Settings, load_settings
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import (
    DocumentIngestionError,
    DocumentIngestionResult,
    SourceDocument,
)
from app.infrastructure.ingestion.email_ingestor import EmailIngestor
from app.infrastructure.ingestion.service import DocumentIngestionService
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow
from app.templates import ObsidianMarkdownGenerator


def _write_eml(
    path: Path,
    *,
    attachments: tuple[tuple[str, bytes], ...] = (),
    subject: str = "Test Email",
    body: str = "Body text.",
) -> Path:
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 21 Jul 2026 10:00:00 +0000"
    msg["Subject"] = subject
    msg.set_content(body)
    for filename, payload in attachments:
        if filename.endswith(".txt"):
            maintype, subtype = "text", "plain"
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)
    path.write_bytes(msg.as_bytes())
    return path


def _nested_eml_part(inner_bytes: bytes) -> MIMEBase:
    part = MIMEBase("message", "rfc822")
    part.set_payload(inner_bytes)
    part["Content-Disposition"] = 'attachment; filename="inner.eml"'
    part["Content-Transfer-Encoding"] = "7bit"
    return part


def _inner_email() -> EmailMessage:
    inner = EmailMessage()
    inner["From"] = "sender@example.com"
    inner["To"] = "recipient@example.com"
    inner["Date"] = "Mon, 21 Jul 2026 10:00:00 +0000"
    inner["Subject"] = "Inner Email"
    inner.set_content("Inner body.")
    inner.add_attachment(
        b"nested attachment", maintype="text", subtype="plain", filename="nested.txt",
    )
    return inner


def _write_eml_with_nested_email(path: Path) -> Path:
    outer = MIMEMultipart()
    outer["From"] = "sender@example.com"
    outer["To"] = "recipient@example.com"
    outer["Date"] = "Mon, 21 Jul 2026 10:00:00 +0000"
    outer["Subject"] = "Outer Email"
    outer.attach(MIMEText("Outer body.", "plain"))
    outer.attach(_nested_eml_part(_inner_email().as_bytes()))
    path.write_bytes(outer.as_bytes())
    return path


def _settings(**metadata_kwargs: object) -> Settings:
    base = load_settings()
    return base.model_copy(
        update={
            "intelligence": IntelligenceSettings(
                metadata=MetadataSettings(**metadata_kwargs)  # type: ignore[arg-type]
            )
        }
    )


class RecordingProcessor:
    """Fake AI processor that records every document it is handed."""

    def __init__(self) -> None:
        self.documents: list[SourceDocument] = []

    def process(self, document: SourceDocument) -> AIProcessingResult:
        self.documents.append(document)
        return AIProcessingResult(document=document, analysis=_analysis(document.text), attempts=1)


class _FailingChildProcessor:
    """Fake AI processor that raises on child documents only."""

    def __init__(self) -> None:
        self.documents: list[SourceDocument] = []

    def process(self, document: SourceDocument) -> AIProcessingResult:
        if "parent_id" in document.metadata.extra:
            raise RuntimeError("attachment processing failed")
        self.documents.append(document)
        return AIProcessingResult(document=document, analysis=_analysis(document.text), attempts=1)


class _ParentThenFailingService:
    """Ingestion service stub: parent succeeds once, then every child fails."""

    def __init__(self, parent_document: SourceDocument) -> None:
        self._parent_document = parent_document
        self.calls = 0

    def ingest(self, source: str | Path) -> DocumentIngestionResult:
        if self.calls == 0:
            self.calls += 1
            return DocumentIngestionResult(document=self._parent_document)
        return DocumentIngestionResult(
            error=DocumentIngestionError(
                source=str(source),
                source_path=Path(str(source)) if not isinstance(source, Path) else source,
                source_type="email",
                reason="1 MB size limit.",
            )
        )


def _workflow(
    tmp_path: Path,
    *,
    settings: Settings | None = None,
) -> tuple[IngestionWorkflow, RecordingProcessor]:
    processor = RecordingProcessor()
    workflow = IngestionWorkflow(
        ingestion_service=DocumentIngestionService(settings=settings),
        processor=processor,
        note_generator=ObsidianMarkdownGenerator(),
        writer=VaultWriter(tmp_path / "vault"),
        settings=settings,
    )
    return workflow, processor


def _attachment_paths(document: SourceDocument) -> list[str]:
    return list(document.metadata.extra.get("attachment_paths") or [])


def _assert_cleaned(paths: list[str]) -> None:
    for path_str in paths:
        candidate = Path(path_str)
        if candidate.is_file():
            candidate.unlink()
        try:
            candidate.parent.rmdir()
        except OSError:
            pass
    for path_str in paths:
        assert not Path(path_str).exists()


class TestEmailIngestorAttachments:
    def test_extracts_attachments_to_temp_files(self, tmp_path: Path) -> None:
        path = _write_eml(
            tmp_path / "mail.eml",
            attachments=(("a.txt", b"alpha"), ("b.txt", b"beta")),
        )
        document = EmailIngestor().ingest(path)

        assert document.metadata.extra["attachments"] == ["a.txt", "b.txt"]
        paths = _attachment_paths(document)
        assert len(paths) == 2
        assert all(Path(p).is_file() for p in paths)
        _assert_cleaned(paths)

    def test_plain_email_has_no_attachment_keys(self, tmp_path: Path) -> None:
        document = EmailIngestor().ingest(_write_eml(tmp_path / "plain.eml"))
        assert "attachments" not in document.metadata.extra
        assert "attachment_paths" not in document.metadata.extra

    def test_attachments_disabled_via_email_attachments_setting(self, tmp_path: Path) -> None:
        path = _write_eml(tmp_path / "mail.eml", attachments=(("a.txt", b"alpha"),))
        ingestor = EmailIngestor(metadata=MetadataSettings(email_attachments=False))
        assert "attachments" not in ingestor.ingest(path).metadata.extra

    def test_attachments_disabled_via_enabled_setting(self, tmp_path: Path) -> None:
        path = _write_eml(tmp_path / "mail.eml", attachments=(("a.txt", b"alpha"),))
        ingestor = EmailIngestor(metadata=MetadataSettings(enabled=False))
        assert "attachments" not in ingestor.ingest(path).metadata.extra

    def test_inline_parts_not_extracted(self, tmp_path: Path) -> None:
        msg = MIMEMultipart()
        msg["From"] = "a@example.com"
        msg["To"] = "b@example.com"
        msg["Subject"] = "Inline"
        msg.attach(MIMEText("Body.", "plain"))
        inline = MIMEBase("application", "octet-stream")
        inline.set_payload(b"inline data")
        inline["Content-Disposition"] = 'inline; filename="inline.txt"'
        msg.attach(inline)
        path = tmp_path / "inline.eml"
        path.write_bytes(msg.as_bytes())

        document = EmailIngestor().ingest(path)
        assert "attachments" not in document.metadata.extra

    def test_path_traversal_filename_sanitized(self, tmp_path: Path) -> None:
        path = _write_eml(tmp_path / "mail.eml", attachments=(("../evil.txt", b"x"),))
        document = EmailIngestor().ingest(path)

        assert document.metadata.extra["attachments"] == ["evil.txt"]
        written = Path(_attachment_paths(document)[0])
        assert written.name == "evil.txt"
        assert written.parent.name.startswith("pam_email_attachments_")
        _assert_cleaned([str(written)])

    def test_duplicate_filenames_deduped(self, tmp_path: Path) -> None:
        path = _write_eml(
            tmp_path / "mail.eml",
            attachments=(("a.txt", b"one"), ("a.txt", b"two")),
        )
        document = EmailIngestor().ingest(path)
        assert document.metadata.extra["attachments"] == ["a.txt", "a-1.txt"]
        _assert_cleaned(_attachment_paths(document))

    def test_nested_email_attachment_serialized(self, tmp_path: Path) -> None:
        path = _write_eml_with_nested_email(tmp_path / "outer.eml")
        outer = EmailIngestor().ingest(path)

        assert outer.metadata.extra["attachments"] == ["inner.eml"]
        inner_path = Path(_attachment_paths(outer)[0])
        inner = EmailIngestor().ingest(inner_path)
        assert inner.source_type == "email"
        assert inner.metadata.extra["attachments"] == ["nested.txt"]
        _assert_cleaned([str(inner_path), *_attachment_paths(inner)])


class TestWorkflowAttachmentIngestion:
    def test_run_ingests_attachments_as_children(self, tmp_path: Path) -> None:
        eml = _write_eml(
            tmp_path / "mail.eml",
            attachments=(("a.txt", b"alpha content"), ("b.txt", b"beta content")),
        )
        workflow, processor = _workflow(tmp_path)

        result = workflow.run(eml, expected_source_type="email")

        assert len(processor.documents) == 3
        parent_id = str(eml.expanduser().resolve())
        assert "parent_id" not in processor.documents[0].metadata.extra
        assert processor.documents[1].metadata.extra["parent_id"] == parent_id
        assert processor.documents[2].metadata.extra["parent_id"] == parent_id
        assert {d.text for d in processor.documents[1:]} == {"alpha content", "beta content"}
        assert result.write_result.created is True
        _assert_cleaned(_attachment_paths(result.document))

    def test_non_email_document_untouched(self, tmp_path: Path) -> None:
        source = tmp_path / "note.md"
        source.write_text("# Local Memory\n\nPlain text.", encoding="utf-8")
        workflow, processor = _workflow(tmp_path)

        result = workflow.run(source, expected_source_type="markdown")

        assert len(processor.documents) == 1
        assert "attachment_paths" not in processor.documents[0].metadata.extra
        assert result.write_result.created is True

    def test_max_attachments_caps_children(self, tmp_path: Path) -> None:
        settings = _settings(max_attachments=1)
        eml = _write_eml(
            tmp_path / "mail.eml",
            attachments=(("a.txt", b"alpha content"), ("b.txt", b"beta content")),
        )
        workflow, processor = _workflow(tmp_path, settings=settings)

        result = workflow.run(eml, expected_source_type="email")

        assert len(processor.documents) == 2
        assert {d.text for d in processor.documents[1:]} == {"alpha content"}
        _assert_cleaned(_attachment_paths(result.document))

    def test_attachments_disabled_skips_children(self, tmp_path: Path) -> None:
        settings = _settings(email_attachments=False)
        eml = _write_eml(tmp_path / "mail.eml", attachments=(("a.txt", b"alpha content"),))
        workflow, processor = _workflow(tmp_path, settings=settings)

        workflow.run(eml, expected_source_type="email")

        assert len(processor.documents) == 1

    def test_child_failure_skipped_and_cleaned(self, tmp_path: Path) -> None:
        eml = _write_eml(tmp_path / "mail.eml", attachments=(("a.txt", b"alpha content"),))
        parent = EmailIngestor().ingest(eml)
        processor = RecordingProcessor()
        workflow = IngestionWorkflow(
            ingestion_service=_ParentThenFailingService(parent),  # type: ignore[arg-type]
            processor=processor,
            note_generator=ObsidianMarkdownGenerator(),
            writer=VaultWriter(tmp_path / "vault"),
        )

        workflow.run(eml)

        assert len(processor.documents) == 1
        _assert_cleaned(_attachment_paths(parent))

    def test_child_processing_failure_skipped_and_cleaned(self, tmp_path: Path) -> None:
        """A failing child (AI step) must not fail the parent email."""
        eml = _write_eml(tmp_path / "mail.eml", attachments=(("a.txt", b"alpha content"),))
        parent = EmailIngestor().ingest(eml)
        processor = _FailingChildProcessor()
        workflow = IngestionWorkflow(
            ingestion_service=DocumentIngestionService(),
            processor=processor,  # type: ignore[arg-type]
            note_generator=ObsidianMarkdownGenerator(),
            writer=VaultWriter(tmp_path / "vault"),
        )

        result = workflow.run(eml)

        assert len(processor.documents) == 1
        assert result.write_result.created is True
        _assert_cleaned(_attachment_paths(parent))

    def test_nested_email_ingested_once_no_infinite_recursion(self, tmp_path: Path) -> None:
        eml = _write_eml_with_nested_email(tmp_path / "outer.eml")
        workflow, processor = _workflow(tmp_path)

        workflow.run(eml, expected_source_type="email")

        assert len(processor.documents) == 2
        inner = processor.documents[1]
        assert inner.source_type == "email"
        assert inner.metadata.extra["parent_id"] == str(eml.expanduser().resolve())
        assert inner.metadata.extra["attachments"] == ["nested.txt"]
        _assert_cleaned(_attachment_paths(processor.documents[0]))
        _assert_cleaned(_attachment_paths(inner))


def _analysis(text: str) -> DocumentAnalysis:
    title = "Note-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    payload: dict[str, Any] = {
        "suggested_note_title": title,
        "summary": {
            "short": "A short summary.",
            "detailed": "A detailed summary.",
        },
        "key_concepts": [
            {
                "name": "Concept",
                "explanation": "An explanation.",
                "importance": "high",
            }
        ],
        "definitions": [
            {
                "term": "Term",
                "definition": "A definition.",
            }
        ],
        "important_entities": [
            {
                "name": "Entity",
                "type": "other",
                "description": "A description.",
            }
        ],
        "tags": ["test"],
        "related_topics": [
            {
                "topic": "Topic",
                "reason": "A reason.",
            }
        ],
    }
    return DocumentAnalysis.model_validate(payload)
