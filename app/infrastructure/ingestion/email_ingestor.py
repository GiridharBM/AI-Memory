"""Ingestor for email files (.eml, .msg)."""

from __future__ import annotations

import email
import email.policy
import shutil
import tempfile
from pathlib import Path

from app.core.config import MetadataSettings
from app.core.logging import get_logger
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import clean_text, file_timestamp

logger = get_logger(__name__)


class EmailIngestor(BaseIngestor):
    """Ingest email files by extracting headers, body, and attachments.

    ``Content-Disposition: attachment`` parts are written to a temporary
    directory and exposed via ``metadata.extra`` under ``attachments``
    (filenames) and ``attachment_paths`` (temp file paths). The caller (the
    ingestion workflow) owns re-ingesting those child sources and cleaning
    the temp directory up afterwards (P2-208).
    """

    source_type = "email"
    supported_suffixes = (".eml",)

    def __init__(self, metadata: MetadataSettings | None = None) -> None:
        self._metadata_settings = metadata or MetadataSettings()

    def ingest(self, source: SourceReference) -> SourceDocument:
        path = require_path_source(source, ingestor_name="EmailIngestor")
        try:
            raw = path.read_bytes()
            msg = email.message_from_bytes(raw, policy=email.policy.default)
        except Exception as exc:
            raise IngestionError(f"Failed to parse email '{path.name}'.") from exc

        subject = str(msg.get("subject", ""))
        sender = str(msg.get("from", ""))
        date = str(msg.get("date", ""))
        to = str(msg.get("to", ""))

        parts: list[str] = []
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    payload = part.get_content()
                    if isinstance(payload, str):
                        parts.append(payload)
                elif ctype == "text/html" and not parts:
                    payload = part.get_content()
                    if isinstance(payload, str):
                        import re
                        text = re.sub(r"<[^>]+>", " ", payload)
                        parts.append(re.sub(r"\s+", " ", text).strip())
        else:
            payload = msg.get_content()
            if isinstance(payload, str):
                parts.append(payload)

        body = "\n\n".join(parts)
        cleaned = clean_text(body)

        header_block = f"From: {sender}\nTo: {to}\nDate: {date}\nSubject: {subject}"
        full_text = f"{header_block}\n\n{cleaned}" if cleaned else header_block

        document = SourceDocument(
            source=str(path),
            source_path=path,
            source_type=self.source_type,
            filename=path.name,
            text=full_text,
            metadata=DocumentMetadata(
                title=subject,
                created_at=file_timestamp(path),
                modified_at=file_timestamp(path),
                extra={
                    "subject": subject,
                    "from": sender,
                    "to": to,
                    "date": date,
                },
            ),
        )

        if self._metadata_settings.enabled and self._metadata_settings.email_attachments:
            document = self._attach_extracted_attachments(document, msg)
        return document

    def _attach_extracted_attachments(
        self, document: SourceDocument, msg: email.message.Message,
    ) -> SourceDocument:
        if not msg.is_multipart():
            return document
        names, paths = self._extract_attachments(msg)
        if not paths:
            return document
        extra = dict(document.metadata.extra)
        extra["attachments"] = names
        extra["attachment_paths"] = paths
        return document.model_copy(
            update={"metadata": document.metadata.model_copy(update={"extra": extra})}
        )

    def _extract_attachments(self, msg: email.message.Message) -> tuple[list[str], list[str]]:
        temp_dir = Path(tempfile.mkdtemp(prefix="pam_email_attachments_"))
        names: list[str] = []
        paths: list[str] = []
        for part in msg.iter_attachments():
            if part.get_content_disposition() != "attachment":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                nested = part.get_content()
                if not isinstance(nested, email.message.Message):
                    continue
                payload = nested.as_bytes()
            if payload is None:
                continue
            filename = _safe_attachment_name(part.get_filename() or f"attachment-{len(names) + 1}")
            filename = _unique_name(filename, names)
            child = temp_dir / filename
            try:
                child.write_bytes(payload)
            except OSError:
                logger.warning(
                    "Skipping un-writable email attachment.",
                    extra={"filename": filename},
                )
                continue
            names.append(filename)
            paths.append(str(child))
        if not paths:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return names, paths


def _safe_attachment_name(filename: str) -> str:
    name = Path(filename).name.strip()
    return name or f"attachment-{abs(hash(filename))}"


def _unique_name(filename: str, existing: list[str]) -> str:
    if filename not in existing:
        return filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    candidate = f"{stem}-{counter}{suffix}"
    while candidate in existing:
        counter += 1
        candidate = f"{stem}-{counter}{suffix}"
    return candidate
