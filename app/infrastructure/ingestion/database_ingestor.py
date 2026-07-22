"""Ingestor for database files (.sqlite, .db)."""

from __future__ import annotations

import sqlite3

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


class DatabaseIngestor(BaseIngestor):
    """Ingest SQLite database files by extracting schema and sample data."""

    source_type = "database"
    supported_suffixes = (".sqlite", ".db")

    def ingest(self, source: SourceReference) -> SourceDocument:
        path = require_path_source(source, ingestor_name="DatabaseIngestor")
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                cursor = conn.cursor()

                # Get all tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row[0] for row in cursor.fetchall()]

                parts: list[str] = []
                parts.append(f"Database: {path.name}")
                parts.append(f"Tables: {', '.join(tables)}")
                parts.append("")

                for table in tables:
                    # Schema
                    cursor.execute(f"PRAGMA table_info('{table}')")
                    columns = cursor.fetchall()
                    col_defs = [f"  {col[1]} ({col[2]})" for col in columns]
                    parts.append(f"Table: {table}")
                    parts.append("Schema:")
                    parts.extend(col_defs)

                    # Row count
                    cursor.execute(f"SELECT COUNT(*) FROM '{table}'")
                    count = cursor.fetchone()[0]
                    parts.append(f"Rows: {count}")

                    # Sample data (first 5 rows)
                    if count > 0:
                        cursor.execute(f"SELECT * FROM '{table}' LIMIT 5")
                        sample_rows = cursor.fetchall()
                        col_names = [col[1] for col in columns]
                        parts.append(f"Sample ({min(5, count)} of {count} rows):")
                        parts.append(" | ".join(col_names))
                        for row in sample_rows:
                            parts.append(" | ".join(str(v) for v in row))
                    parts.append("")
            finally:
                conn.close()

            cleaned = clean_text("\n".join(parts))

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
                    extra={
                        "table_count": len(tables),
                        "tables": tables,
                    },
                ),
            )
        except sqlite3.Error as exc:
            raise IngestionError(f"Failed to read database '{path.name}'.") from exc
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError(f"Failed to process database '{path.name}'.") from exc
