"""Canonical file extension sets used across the application."""

from __future__ import annotations

CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rb", ".rs",
    ".php", ".sh", ".bash",
})

IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff",
})

AUDIO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp3", ".wav", ".m4a", ".flac", ".ogg",
})

VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp4", ".mkv", ".mov", ".avi", ".webm",
})

DOCX_EXTENSIONS: frozenset[str] = frozenset({".docx"})
PPTX_EXTENSIONS: frozenset[str] = frozenset({".pptx"})
SPREADSHEET_EXTENSIONS: frozenset[str] = frozenset({".xls", ".xlsx"})
