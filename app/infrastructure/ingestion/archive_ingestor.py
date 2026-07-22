"""Ingestor for archive files (.zip, .tar, .gz, .7z, .rar)."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

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


class ArchiveIngestor(BaseIngestor):
    """Ingest archive files by extracting file listings."""

    source_type = "archive"
    supported_suffixes = (".zip", ".tar", ".gz", ".7z", ".rar")

    def ingest(self, source: SourceReference) -> SourceDocument:
        path = require_path_source(source, ingestor_name="ArchiveIngestor")
        suffix = path.suffix.lower()

        try:
            if suffix == ".zip":
                listing = self._list_zip(path)
            elif suffix in (".tar", ".gz"):
                listing = self._list_tar(path)
            else:
                listing = self._basic_listing(path)
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError(f"Failed to read archive '{path.name}'.") from exc

        cleaned = clean_text(listing)
        return SourceDocument(
            source=str(path),
            source_path=path,
            source_type=self.source_type,
            filename=path.name,
            text=cleaned,
            metadata=DocumentMetadata(
                title=path.stem,
                created_at=file_timestamp(path),
                modified_at=file_timestamp(path),
                extra={"format": suffix.lstrip(".")},
            ),
        )

    @staticmethod
    def _list_zip(path: Path) -> str:
        if not zipfile.is_zipfile(path):
            raise IngestionError(f"File '{path.name}' is not a valid ZIP archive.")
        with zipfile.ZipFile(path, "r") as zf:
            entries = zf.infolist()
            total_size = sum(e.file_size for e in entries)
            lines = [
                f"Archive: {path.name}",
                "Format: ZIP",
                f"Files: {len(entries)}",
                f"Uncompressed Size: {total_size:,} bytes",
                "",
                "Contents:",
            ]
            for entry in sorted(entries, key=lambda e: e.filename):
                size = f"{entry.file_size:>10,}" if not entry.is_dir() else "      <DIR>"
                lines.append(f"  {size}  {entry.filename}")
            return "\n".join(lines)

    @staticmethod
    def _list_tar(path: Path) -> str:
        if tarfile.is_tarfile(path):
            with tarfile.open(path, "r:*") as tf:
                members = tf.getmembers()
                total_size = sum(m.size for m in members)
                lines = [
                    f"Archive: {path.name}",
                    "Format: TAR",
                    f"Files: {len(members)}",
                    f"Uncompressed Size: {total_size:,} bytes",
                    "",
                    "Contents:",
                ]
                for member in sorted(members, key=lambda m: m.name):
                    size = f"{member.size:>10,}" if member.isfile() else "      <DIR>"
                    lines.append(f"  {size}  {member.name}")
                return "\n".join(lines)
        raise IngestionError(f"File '{path.name}' is not a valid TAR archive.")

    @staticmethod
    def _basic_listing(path: Path) -> str:
        return (
            f"Archive: {path.name}\n"
            f"Format: {path.suffix.lstrip('.').upper()}\n"
            f"Size: {path.stat().st_size:,} bytes\n\n"
            f"Note: 7z/RAR listing requires additional tools. "
            f"File metadata recorded."
        )
