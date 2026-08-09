"""Table extraction subsystem — extractors, registry, and Markdown renderer (M2.4).

Architecture mirrors the M2.3 structure package: one module per concern behind a
composition root. Extracted tables ride ``metadata.extra["tables"]`` on the
enriched document (C5) — ``ProcessedDocument`` is never modified (R-1 precedent).
"""

from app.infrastructure.document_intelligence.tables.extractor import (
    extract_tables,
    get_default_table_extractor,
    get_table_extractor,
)
from app.infrastructure.document_intelligence.tables.render import (
    MarkdownTableRenderer,
    render_tables_to_markdown,
)

__all__ = [
    "extract_tables",
    "get_default_table_extractor",
    "get_table_extractor",
    "MarkdownTableRenderer",
    "render_tables_to_markdown",
]
