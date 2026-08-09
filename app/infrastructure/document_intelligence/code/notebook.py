"""Jupyter notebook parser (P2-605).

Parses the full notebook dict (output of ``json.loads``) into a
:class:`NotebookStructure` with ordered typed cells. Tolerates malformed
cells and never raises.
"""

from __future__ import annotations

import logging

from app.domain.document_intelligence import NotebookCell, NotebookStructure

logger = logging.getLogger(__name__)

# ponytail: parser default until config wiring overrides it (P2-606)
_MAX_CELL_OUTPUTS = 100

_TRUNCATED = "[truncated]"
_VALID_CELL_TYPES = ("markdown", "code", "raw")


def _cell_id(cell: dict, index: int) -> str:
    """Cell id from the ``id`` field, falling back to the 0-based index."""
    raw_id = cell.get("id")
    return str(raw_id) if raw_id else str(index)


def _cell_source(cell: dict) -> str:
    """Join ``source`` (list of lines or a single string) into one string."""
    source = cell.get("source")
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source) if source is not None else ""


def _output_text(output: object) -> str:
    """Best-effort string form of an ipynb output entry."""
    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, list):
            return "".join(str(part) for part in text)
        if text:
            return str(text)
    return str(output)


def _cell_outputs(cell: dict, cap: int) -> list[str]:
    """Output entries capped at *cap*; excess replaced with the truncated marker."""
    outputs = cell.get("outputs")
    if not isinstance(outputs, list):
        return []
    capped = [_output_text(output) for output in outputs[:cap]]
    if len(outputs) > cap:
        capped.append(_TRUNCATED)
    return capped


class NotebookParser:
    """Parse a full Jupyter notebook dict into a :class:`NotebookStructure`."""

    def parse(self, raw: dict, max_cell_outputs: int | None = None) -> NotebookStructure:
        cap = _MAX_CELL_OUTPUTS if max_cell_outputs is None else max_cell_outputs
        if not isinstance(raw, dict):
            logger.warning("Notebook input is not a dict; returning empty structure")
            return NotebookStructure()

        raw_cells = raw.get("cells")
        if not isinstance(raw_cells, list):
            raw_cells = []

        cells: list[NotebookCell] = []
        for index, cell in enumerate(raw_cells):
            if not isinstance(cell, dict):
                logger.warning("Skipping notebook cell %d: not a dict", index)
                continue
            cell_type = cell.get("cell_type")
            if cell_type not in _VALID_CELL_TYPES:
                logger.warning(
                    "Skipping notebook cell %d: missing/invalid cell_type %r", index, cell_type
                )
                continue
            execution_count = cell.get("execution_count")
            cells.append(
                NotebookCell(
                    id=_cell_id(cell, index),
                    type=cell_type,
                    source=_cell_source(cell),
                    outputs=_cell_outputs(cell, cap),
                    execution_count=(
                        execution_count if isinstance(execution_count, int) else None
                    ),
                )
            )

        metadata = raw.get("metadata") if isinstance(raw, dict) else {}
        kernelspec = metadata.get("kernelspec", {}) if isinstance(metadata, dict) else {}
        language_info = (
            metadata.get("language_info", {}) if isinstance(metadata, dict) else {}
        )

        return NotebookStructure(
            cells=cells,
            kernel=str(kernelspec.get("display_name", "")) if isinstance(kernelspec, dict) else "",
            language=(
                str(language_info.get("name", "")) if isinstance(language_info, dict) else ""
            ),
        )


def parse_notebook(raw: dict, max_cell_outputs: int | None = None) -> NotebookStructure:
    """Parse a full Jupyter notebook dict (output of ``json.loads``).

    *max_cell_outputs* (default ``_MAX_CELL_OUTPUTS``) caps per-cell outputs;
    entries beyond the cap are replaced with a ``[truncated]`` marker.
    """
    return NotebookParser().parse(raw, max_cell_outputs)


__all__ = ["NotebookParser", "parse_notebook"]
