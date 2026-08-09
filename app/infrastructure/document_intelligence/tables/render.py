"""Markdown table renderer (frozen §4.4 P2-406)."""

from __future__ import annotations

from app.domain.document_intelligence import Table


class MarkdownTableRenderer:
    """Render a Table as a GitHub-flavored Markdown table (frozen §2.4)."""

    def to_markdown(self, table: Table) -> str:
        """Return the table as ``| col | col |`` Markdown; ``""`` when empty.

        Cells are escaped: ``|`` → ``\\|`` and embedded newlines → ``<br>`` so
        the rendered table stays a valid Markdown grid (frozen §2.4 escaping).
        """
        header = [_escape(cell.value) for cell in table.header.cells]
        rows = [[_escape(cell.value) for cell in row.cells] for row in table.rows]
        if not header and not rows:
            return ""
        width = max(len(header), *(len(row) for row in rows), 0)
        if width == 0:
            return ""
        header = list(header) + [""] * (width - len(header))

        def _pad(cells: list[str]) -> list[str]:
            return list(cells) + [""] * (width - len(cells))

        lines = [_render_row(header), _render_row(["---"] * width)]
        lines.extend(_render_row(_pad(row)) for row in rows)
        return "\n".join(lines)


def _render_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def render_tables_to_markdown(tables: list[Table]) -> list[str]:
    """Render tables to a list of Markdown strings (headers included)."""
    renderer = MarkdownTableRenderer()
    return [markdown for table in tables if (markdown := renderer.to_markdown(table))]
