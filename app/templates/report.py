"""Deterministic Markdown rendering for generated reports.

Pure functions over the structured ``Report`` model — no LLM calls, no
I/O. Mirrors the section-assembly idiom of ``templates/obsidian_note.py``.
"""

from __future__ import annotations

from app.domain.generation_documents import Report, ReportSection, ReportTable


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _render_table(table: ReportTable) -> str:
    header = [_escape_cell(cell) for cell in table.headers]
    width = len(header)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in table.rows:
        padded = [_escape_cell(cell) for cell in row] + [""] * (width - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _render_section(section: ReportSection) -> list[str]:
    parts = [f"## {section.heading}", ""]
    for paragraph in section.paragraphs:
        parts.append(paragraph)
        parts.append("")
    for bullet in section.bullets:
        parts.append(f"- {bullet}")
    if section.bullets:
        parts.append("")
    if section.table is not None:
        parts.append(_render_table(section.table))
        parts.append("")
    return parts


def render_report_markdown(report: Report) -> str:
    """Render a structured report as deterministic Markdown."""

    parts = [f"# {report.title}", "", report.summary.strip(), ""]
    for section in report.sections:
        parts.extend(_render_section(section))
    references = [ref for section in report.sections for ref in section.references]
    if references:
        parts.append("### References")
        parts.append("")
        for index, reference in enumerate(references, 1):
            parts.append(f"- [{index}] {reference}")
        parts.append("")
    return "\n".join(parts).rstrip()
