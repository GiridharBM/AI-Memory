"""Shared helpers for source ingestion."""

from __future__ import annotations

import re
import textwrap
from datetime import UTC, datetime
from pathlib import Path

_CODE_BLOCK_TOKEN_TEMPLATE = "__PAM_CODE_BLOCK_{index}__"
_LIST_PATTERN = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s*(.*)$")
_TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?[\s:-]+(?:\|[\s:-]+)+\|?\s*$")


def clean_text(value: str) -> str:
    """Normalize text while preserving headings, lists, and fenced code blocks."""

    normalized = textwrap.dedent(value)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    protected_text, code_blocks = _protect_code_blocks(normalized)

    cleaned_lines: list[str] = []
    blank_streak = 0

    for raw_line in protected_text.split("\n"):
        processed_line = _normalize_line(raw_line)

        if not processed_line:
            if blank_streak < 1:
                cleaned_lines.append("")
            blank_streak += 1
            continue

        cleaned_lines.append(processed_line)
        blank_streak = 0

    cleaned_text = "\n".join(cleaned_lines).strip()
    cleaned_text = _restore_code_blocks(cleaned_text, code_blocks)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
    return cleaned_text.strip()


def file_timestamp(source_path: Path) -> datetime:
    """Return the filesystem modification time in UTC."""

    return datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)


def _protect_code_blocks(text: str) -> tuple[str, list[str]]:
    lines = text.split("\n")
    output: list[str] = []
    code_blocks: list[str] = []
    current_block: list[str] = []
    inside_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            current_block.append(_rstrip_trailing_whitespace(line))
            if inside_code_block:
                token = _CODE_BLOCK_TOKEN_TEMPLATE.format(index=len(code_blocks))
                code_blocks.append("\n".join(current_block).strip())
                output.append(token)
                current_block = []
                inside_code_block = False
            else:
                inside_code_block = True
            continue

        if inside_code_block:
            current_block.append(_rstrip_trailing_whitespace(line))
            continue

        output.append(line)

    if current_block:
        token = _CODE_BLOCK_TOKEN_TEMPLATE.format(index=len(code_blocks))
        code_blocks.append("\n".join(current_block).strip())
        output.append(token)

    return "\n".join(output), code_blocks


def _restore_code_blocks(text: str, code_blocks: list[str]) -> str:
    restored = text
    for index, code_block in enumerate(code_blocks):
        token = _CODE_BLOCK_TOKEN_TEMPLATE.format(index=index)
        restored = restored.replace(token, code_block)
    return restored


def _normalize_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""

    if _is_code_block_token(stripped):
        return stripped

    heading_match = _HEADING_PATTERN.match(stripped)
    if heading_match:
        heading_marks, title = heading_match.groups()
        normalized_title = _collapse_inline_whitespace(title)
        return f"{heading_marks} {normalized_title}".rstrip()

    if _LIST_PATTERN.match(line):
        return _normalize_list_item(line)

    if stripped.startswith(">"):
        return _normalize_blockquote(stripped)

    if "|" in stripped and not _TABLE_SEPARATOR_PATTERN.match(stripped):
        return _normalize_table_row(stripped)

    if _TABLE_SEPARATOR_PATTERN.match(stripped):
        return re.sub(r"\s+", "-", stripped.replace(" ", ""))

    return _collapse_inline_whitespace(stripped)


def _normalize_list_item(line: str) -> str:
    match = _LIST_PATTERN.match(line)
    if match is None:
        return _collapse_inline_whitespace(line.strip())

    indent, marker = match.groups()
    content = line[match.end():]
    normalized_content = _collapse_inline_whitespace(content)
    normalized_indent = " " * _normalized_indent_width(indent)
    return f"{normalized_indent}{marker} {normalized_content}".rstrip()


def _normalize_blockquote(stripped_line: str) -> str:
    quote_depth = 0
    remainder = stripped_line
    while remainder.startswith(">"):
        quote_depth += 1
        remainder = remainder[1:].lstrip()
    prefix = "> " * quote_depth
    return f"{prefix}{_collapse_inline_whitespace(remainder)}".rstrip()


def _normalize_table_row(stripped_line: str) -> str:
    cells = [cell.strip() for cell in stripped_line.strip("|").split("|")]
    normalized_cells = " | ".join(cells)
    return f"| {normalized_cells} |"


def _collapse_inline_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def _normalized_indent_width(indent: str) -> int:
    expanded = indent.replace("\t", "    ")
    width = len(expanded)
    return (width // 2) * 2


def _is_code_block_token(value: str) -> bool:
    return value.startswith("__PAM_CODE_BLOCK_") and value.endswith("__")


def _rstrip_trailing_whitespace(value: str) -> str:
    return value.rstrip(" \t")
