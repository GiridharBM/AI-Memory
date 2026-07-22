"""Ingestor for email files (.eml, .msg)."""

from __future__ import annotations

import email
import email.policy

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
    """Ingest email files by extracting headers and body."""

    source_type = "email"
    supported_suffixes = (".eml",)

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

        return SourceDocument(
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
