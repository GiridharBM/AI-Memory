"""Ingestor for Jupyter notebook files (.ipynb)."""

from __future__ import annotations

import json

from app.core.logging import get_logger
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.code import parse_notebook
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import clean_text, file_timestamp

logger = get_logger(__name__)


class NotebookIngestor(BaseIngestor):
    """Ingest Jupyter notebooks by extracting cell contents."""

    source_type = "notebook"
    supported_suffixes = (".ipynb",)

    def __init__(self, *, max_cell_outputs: int | None = None) -> None:
        """Cap cell outputs via ``CodeSettings.max_cell_outputs``; None = parser default."""
        self._max_cell_outputs = max_cell_outputs

    def ingest(self, source: SourceReference) -> SourceDocument:
        path = require_path_source(source, ingestor_name="NotebookIngestor")
        try:
            raw = path.read_text(encoding="utf-8")
            notebook = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Invalid JSON in notebook '{path.name}'.") from exc
        except Exception as exc:
            raise IngestionError(f"Failed to read notebook '{path.name}'.") from exc

        cells = notebook.get("cells", [])
        parts: list[str] = []
        for cell in cells:
            cell_type = cell.get("cell_type", "")
            source_lines = cell.get("source", [])
            if isinstance(source_lines, list):
                text = "".join(source_lines)
            else:
                text = str(source_lines)
            if cell_type == "markdown":
                parts.append(text.strip())
            elif cell_type == "code":
                parts.append(f"```python\n{text.strip()}\n```")
            else:
                parts.append(text.strip())

        combined = "\n\n".join(parts)
        cleaned = clean_text(combined)

        kernel = notebook.get("metadata", {}).get("kernelspec", {})
        lang = kernel.get(
            "language",
            notebook.get("metadata", {}).get("language_info", {}).get("name", ""),
        )

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
                    "cell_count": len(cells),
                    "kernel": kernel.get("display_name", ""),
                    "language": lang,
                    "notebook_structure": parse_notebook(notebook, self._max_cell_outputs),
                },
            ),
        )
