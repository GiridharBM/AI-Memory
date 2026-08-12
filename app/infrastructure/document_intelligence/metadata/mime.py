"""MIME detection service (P2-203).

Magic-number sniff (first 512 bytes) with a stdlib fallback table plus an
optional ``python-magic`` enhancement (ADR-001: warning-only if absent).

Precedence (ADR-001): a known extension resolves by extension without reading
content; only extensionless or unknown-extension files are sniffed. When
sniffing, libmagic's generic ``text/plain`` verdict never wins over the
stdlib Markdown heuristic (libmagic does not identify Markdown).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

# Types the stdlib mimetypes table misses (Python 3.14 already maps .md/.eml).
_SUPPLEMENTAL_EXTENSIONS = {
    ".ipynb": "application/x-ipynb+json",
}

_MAGIC_MISSING_WARNED = False


def detect_mime(path: Path) -> str:
    """Return the MIME type for a file path.

    Known extensions return the extension-based type (ADR-001) without
    touching the file. Extensionless/unknown-extension files are sniffed:
    ``python-magic`` when importable, otherwise the stdlib ``_sniff_mime``
    table. Returns ``application/octet-stream`` when nothing is determinable.
    """
    extension_type = _extension_mime(path)
    if extension_type is not None:
        return _normalize_mime_alias(extension_type)

    header = _read_header(path)
    if header is None:
        return "application/octet-stream"

    magic_type = _magic_from_header(header)
    if magic_type is not None and magic_type not in {"text/plain", "application/octet-stream"}:
        return _normalize_mime_alias(magic_type)
    return _normalize_mime_alias(_sniff_mime(header))


def _normalize_mime_alias(mime_type: str) -> str:
    """Normalize MIME aliases to PAM's canonical application-level values."""
    if mime_type == "text/xml":
        return "application/xml"
    return mime_type


def _extension_mime(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in _SUPPLEMENTAL_EXTENSIONS:
        return _SUPPLEMENTAL_EXTENSIONS[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed


def _read_header(path: Path) -> bytes | None:
    try:
        with path.open("rb") as handle:
            return handle.read(512)
    except OSError:
        return None


def _magic_from_header(header: bytes) -> str | None:
    global _MAGIC_MISSING_WARNED
    try:
        import magic  # type: ignore[import-not-found]
    except ImportError:
        if not _MAGIC_MISSING_WARNED:
            _MAGIC_MISSING_WARNED = True
            logger.warning(
                "python-magic is not installed; using the stdlib MIME sniff fallback."
            )
        return None
    try:
        detected = magic.from_buffer(header, mime=True)
    except Exception:
        return None
    return detected or None


def _sniff_mime(header: bytes) -> str:
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "application/zip"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "audio/wav"
    if header.startswith(b"OggS"):
        return "audio/ogg"
    if header.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3")):
        return "audio/mpeg"
    if header.startswith(b"<?xml"):
        return "application/xml"
    stripped = header.lstrip()
    if stripped.startswith((b"<!DOCTYPE html", b"<html")):
        return "text/html"
    if stripped.startswith((b"{", b"[")):
        return "application/json"
    if _is_markdown(header):
        return "text/markdown"
    if _is_plain_text(header):
        return "text/plain"
    return "application/octet-stream"


def _is_markdown(header: bytes) -> bool:
    if b"\x00" in header:
        return False
    text = header.decode("utf-8", errors="replace")
    for line in text.splitlines()[:3]:
        if line.startswith("# "):
            return True
    return text.lstrip().startswith("---")


def _is_plain_text(header: bytes) -> bool:
    if not header:
        return True
    printable = sum(1 for byte in header if byte in b"\t\n\r" or 32 <= byte <= 126)
    return printable / len(header) >= 0.9


__all__ = ["detect_mime"]
