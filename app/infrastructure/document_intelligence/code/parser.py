"""Code parsers and ``parse_code`` dispatcher (P2-603, P2-604).

Python sources are parsed with the stdlib :mod:`ast` module; syntax-invalid
Python and all non-Python sources fall back to the line-based heuristic parser,
which never raises.
"""

from __future__ import annotations

import ast
import logging
import re
from collections.abc import Callable
from typing import Protocol

from app.domain.document_intelligence import (
    CodeClass,
    CodeFunction,
    CodeImport,
    CodeStructure,
)
from app.infrastructure.document_intelligence.code.languages import (
    language_from_filename,
)

logger = logging.getLogger(__name__)

# ponytail: parser default until config wiring overrides it (P2-606)
_MAX_CODE_CHARS = 1_000_000


def _truncate(text: str, filename: str, max_chars: int | None = None) -> str:
    """Truncate *text* to *max_chars* (default ``_MAX_CODE_CHARS``), logging a warning."""
    cap = _MAX_CODE_CHARS if max_chars is None else max_chars
    if len(text) > cap:
        logger.warning("Truncating %s at %d chars (max_code_chars)", filename, cap)
        return text[:cap]
    return text


class CodeParser(Protocol):
    """Minimal contract every code parser implements (frozen spec §4.6)."""

    languages: frozenset[str]

    def parse(self, text: str, filename: str, max_chars: int | None = None) -> CodeStructure: ...


def _line_starts(text: str) -> list[int]:
    """Char offset of the first column of each line (1-indexed by line number)."""
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _imports(node: ast.Import | ast.ImportFrom) -> list[CodeImport]:
    """Map a top-level import statement onto :class:`CodeImport` models."""
    if isinstance(node, ast.Import):
        return [
            CodeImport(
                module=alias.name,
                names=[alias.asname] if alias.asname else [],
            )
            for alias in node.names
        ]
    return [
        CodeImport(
            module=node.module or ".",
            names=[alias.asname or alias.name for alias in node.names],
            level=node.level,
        )
    ]


def _args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """All parameter names in declaration order, including *args/**kwargs."""
    a = node.args
    varargs = [a.vararg] if a.vararg else []
    kwargs = [a.kwarg] if a.kwarg else []
    return [arg.arg for arg in a.posonlyargs + a.args + varargs + a.kwonlyargs + kwargs]


def _to_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, offset: Callable[[int, int], int]
) -> CodeFunction:
    """Build a :class:`CodeFunction` from an ``ast`` function node."""
    end_line = node.end_lineno if node.end_lineno is not None else node.lineno
    end_col = node.end_col_offset if node.end_col_offset is not None else node.col_offset
    return CodeFunction(
        name=node.name,
        args=_args(node),
        docstring=ast.get_docstring(node),
        start_line=node.lineno,
        end_line=end_line,
        start_char=offset(node.lineno, node.col_offset),
        end_char=offset(end_line, end_col),
    )


def _to_class(node: ast.ClassDef, offset: Callable[[int, int], int]) -> CodeClass:
    """Build a :class:`CodeClass` from an ``ast`` class node."""
    methods = [
        _to_function(child, offset)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    end_line = node.end_lineno if node.end_lineno is not None else node.lineno
    end_col = node.end_col_offset if node.end_col_offset is not None else node.col_offset
    return CodeClass(
        name=node.name,
        bases=[ast.unparse(base) for base in node.bases],
        methods=methods,
        docstring=ast.get_docstring(node),
        start_line=node.lineno,
        end_line=end_line,
        start_char=offset(node.lineno, node.col_offset),
        end_char=offset(end_line, end_col),
    )


class _AstCodeParser:
    """Extract imports, functions, classes, and docstrings from Python source."""

    languages: frozenset[str] = frozenset({"python"})

    def parse(self, text: str, filename: str, max_chars: int | None = None) -> CodeStructure:
        text = _truncate(text, filename, max_chars)
        tree = ast.parse(text)
        line_starts = _line_starts(text)

        def offset(line: int, col: int) -> int:
            return line_starts[line - 1] + col

        imports: list[CodeImport] = []
        functions: list[CodeFunction] = []
        classes: list[CodeClass] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.extend(_imports(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(_to_function(node, offset))
            elif isinstance(node, ast.ClassDef):
                classes.append(_to_class(node, offset))

        docstrings: list[str] = []
        module_docstring = ast.get_docstring(tree)
        if module_docstring:
            docstrings.append(module_docstring)
        docstrings.extend(fn.docstring for fn in functions if fn.docstring)
        docstrings.extend(cls.docstring for cls in classes if cls.docstring)
        for cls in classes:
            docstrings.extend(m.docstring for m in cls.methods if m.docstring)

        return CodeStructure(
            language="python",
            imports=imports,
            functions=functions,
            classes=classes,
            docstrings=docstrings,
            char_start=0,
            char_end=len(text),
        )


class _HeuristicCodeParser:
    """Line-based fallback for non-Python and syntax-invalid Python files (P2-604).

    Uses conservative regex patterns to spot functions, classes, and imports.
    Char offsets approximate each match's line; the parser **never raises** —
    unparseable input yields an empty :class:`CodeStructure`.
    """

    languages: frozenset[str] = frozenset()

    _FUNCTION_RE = re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)")
    _CLASS_RE = re.compile(r"^(?:export\s+)?class\s+(\w+)")
    _IMPORT_RE = re.compile(r"^(?:import|from)\s+([\w.]+)")
    _DOCSTRING_RE = re.compile(r'"""(.*?)"""|\'\'\'(.*?)\'\'\'')

    def parse(self, text: str, filename: str, max_chars: int | None = None) -> CodeStructure:
        text = _truncate(text, filename, max_chars)
        language = language_from_filename(filename)
        line_starts = _line_starts(text)
        lines = text.split("\n")

        imports: list[CodeImport] = []
        functions: list[CodeFunction] = []
        classes: list[CodeClass] = []
        docstrings: list[str] = []

        for index, line in enumerate(lines):
            line_no = index + 1
            start_char = line_starts[index]
            end_char = (
                line_starts[index + 1]
                if index + 1 < len(line_starts)
                else len(text)
            )
            stripped = line.strip()

            match = self._FUNCTION_RE.match(stripped)
            if match:
                functions.append(
                    CodeFunction(
                        name=match.group(1),
                        start_line=line_no,
                        end_line=line_no,
                        start_char=start_char,
                        end_char=end_char,
                    )
                )
                continue
            match = self._CLASS_RE.match(stripped)
            if match:
                classes.append(
                    CodeClass(
                        name=match.group(1),
                        start_line=line_no,
                        end_line=line_no,
                        start_char=start_char,
                        end_char=end_char,
                    )
                )
                continue
            match = self._IMPORT_RE.match(stripped)
            if match:
                imports.append(CodeImport(module=match.group(1)))
                continue
            match = self._DOCSTRING_RE.search(line)
            if match:
                docstrings.append(match.group(1) or match.group(2) or "")

        return CodeStructure(
            language=language,
            imports=imports,
            functions=functions,
            classes=classes,
            docstrings=docstrings,
            char_start=0,
            char_end=len(text),
        )


def parse_code(text: str, filename: str, max_chars: int | None = None) -> CodeStructure:
    """Parse *text* as the language inferred from *filename*.

    Python sources use the AST parser; syntax-invalid Python and all other
    languages fall back to the heuristic parser (never raises). *max_chars*
    (default ``_MAX_CODE_CHARS``) truncates oversized sources at parse time
    (frozen §4.6 performance).
    """
    language = language_from_filename(filename)
    parser: CodeParser = (
        _AstCodeParser() if language == "python" else _HeuristicCodeParser()
    )
    try:
        return parser.parse(text, filename, max_chars)
    except SyntaxError:
        logger.warning("Syntax error parsing %s; falling back to heuristic parser", filename)
        return _HeuristicCodeParser().parse(text, filename, max_chars)


__all__ = ["CodeParser", "parse_code"]
