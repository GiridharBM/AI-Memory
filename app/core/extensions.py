"""Canonical file extension sets used across the application."""

from __future__ import annotations

# ── Programming languages ────────────────────────────────────────────────────
CODE_EXTENSIONS: frozenset[str] = frozenset({
    # Mainstream
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".cs", ".go",
    ".rb", ".rs", ".php", ".sh", ".bash",
    # Mobile / systems
    ".kt", ".swift", ".dart", ".scala",
    # Data / scripting
    ".r", ".m", ".ps1", ".sql",
    # Web styles
    ".css", ".scss", ".less", ".vue", ".svelte",
})

# ── Configuration files ─────────────────────────────────────────────────────
CONFIG_EXTENSIONS: frozenset[str] = frozenset({
    ".toml", ".ini", ".cfg", ".conf", ".env",
})

# ── Images ───────────────────────────────────────────────────────────────────
IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".heic", ".svg",
})

# ── Audio ────────────────────────────────────────────────────────────────────
AUDIO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac",
})

# ── Video ────────────────────────────────────────────────────────────────────
VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp4", ".mkv", ".mov", ".avi", ".webm",
})

# ── Documents ────────────────────────────────────────────────────────────────
DOCX_EXTENSIONS: frozenset[str] = frozenset({".docx", ".odt", ".rtf"})
PPTX_EXTENSIONS: frozenset[str] = frozenset({".pptx", ".ppt", ".odp"})
SPREADSHEET_EXTENSIONS: frozenset[str] = frozenset({".xls", ".xlsx", ".ods"})
NOTEBOOK_EXTENSIONS: frozenset[str] = frozenset({".ipynb"})
TEX_EXTENSIONS: frozenset[str] = frozenset({".tex"})
EPUB_EXTENSIONS: frozenset[str] = frozenset({".epub"})

# ── Diagrams ─────────────────────────────────────────────────────────────────
DIAGRAM_EXTENSIONS: frozenset[str] = frozenset({".drawio", ".vsdx", ".mmd"})

# ── Archives ─────────────────────────────────────────────────────────────────
ARCHIVE_EXTENSIONS: frozenset[str] = frozenset({".zip", ".tar", ".gz", ".7z", ".rar"})

# ── Email ────────────────────────────────────────────────────────────────────
EMAIL_EXTENSIONS: frozenset[str] = frozenset({".eml", ".msg"})

# ── Databases ────────────────────────────────────────────────────────────────
DATABASE_EXTENSIONS: frozenset[str] = frozenset({".sqlite", ".db"})

# ── Research ─────────────────────────────────────────────────────────────────
RESEARCH_EXTENSIONS: frozenset[str] = frozenset({".bib", ".ris"})

# ── Web ──────────────────────────────────────────────────────────────────────
WEB_EXTENSIONS: frozenset[str] = frozenset({".html", ".htm", ".xml", ".json", ".rss"})
