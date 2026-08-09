"""Language registry — maps file extensions to language names (P2-602)."""

from __future__ import annotations

from pathlib import PurePosixPath

from app.core.extensions import CODE_EXTENSIONS

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # Mainstream
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".cpp": "c++",
    ".cs": "c#",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    # Mobile / systems
    ".kt": "kotlin",
    ".swift": "swift",
    ".dart": "dart",
    ".scala": "scala",
    # Data / scripting
    ".r": "r",
    ".m": "objective-c",
    ".ps1": "powershell",
    ".sql": "sql",
    # Web styles
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
}

_unmapped = CODE_EXTENSIONS - set(_EXTENSION_TO_LANGUAGE)
if _unmapped:
    raise RuntimeError(f"Unmapped code extensions: {sorted(_unmapped)}")


def language_from_filename(filename: str) -> str:
    """Return the language name for *filename*, or ``"generic"`` if unknown.

    Lookup is case-insensitive (``.PY`` → ``"python"``).
    Only extensions present in :data:`CODE_EXTENSIONS` are mapped.
    """
    suffix = PurePosixPath(filename).suffix.lower()
    return _EXTENSION_TO_LANGUAGE.get(suffix, "generic")
