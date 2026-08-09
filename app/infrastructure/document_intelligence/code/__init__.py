"""Code intelligence subpackage — language registry, parsers (P2-602+)."""

from app.infrastructure.document_intelligence.code.languages import (
    language_from_filename,
)
from app.infrastructure.document_intelligence.code.notebook import (
    NotebookParser,
    parse_notebook,
)
from app.infrastructure.document_intelligence.code.parser import (
    CodeParser,
    parse_code,
)

__all__ = [
    "CodeParser",
    "NotebookParser",
    "language_from_filename",
    "parse_code",
    "parse_notebook",
]
