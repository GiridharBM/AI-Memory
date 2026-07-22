"""Spreadsheet (XLS/XLSX) file ingestor."""

from __future__ import annotations

from pathlib import Path

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import file_timestamp


class SpreadsheetIngestor(BaseIngestor):
    """Read spreadsheet files into normalized source documents."""

    source_type = "spreadsheet"
    supported_suffixes = (".xls", ".xlsx", ".ods")

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="Spreadsheet ingestor")
        text = self._extract_text(source_path)
        resolved_path = source_path.resolve()
        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text=text,
            metadata=DocumentMetadata(
                title=source_path.stem,
                modified_at=file_timestamp(source_path),
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )

    def _extract_text(self, path: Path) -> str:
        try:
            import openpyxl  # type: ignore[import-untyped]

            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            texts: list[str] = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                texts.append(f"Sheet: {sheet_name}")
                for row in ws.iter_rows(values_only=True):
                    row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
                    if row_text.strip():
                        texts.append(row_text)
            wb.close()
            return "\n".join(texts)
        except ImportError:
            raise IngestionError(
                "openpyxl is required for spreadsheet ingestion. Install with: pip install openpyxl"
            )
        except Exception as exc:
            raise IngestionError(f"Unable to read spreadsheet file '{path}'.") from exc
