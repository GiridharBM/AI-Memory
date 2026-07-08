"""Obsidian vault management for generated notes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import get_logger
from app.domain.notes import ObsidianNote

logger = get_logger(__name__)

MANAGED_BEGIN = "<!-- PAM:BEGIN MANAGED -->"
MANAGED_END = "<!-- PAM:END MANAGED -->"
NOTES_FOLDER = "Notes"
INDEX_FILE = "index.md"
OVERVIEW_FILE = "overview.md"
LOG_FILE = "log.md"

_FRONTMATTER_PATTERN = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---\n?", re.DOTALL)


@dataclass(slots=True)
class WikiUpdateResult:
    """Result returned after writing a note into the wiki."""

    note_path: Path
    created: bool
    updated: bool
    index_path: Path
    overview_path: Path
    log_path: Path
    warnings: list[str] = field(default_factory=list)


class WikiManager:
    """Manage generated notes and core wiki files inside an Obsidian vault."""

    def __init__(self, vault_root: Path, *, notes_folder: str = NOTES_FOLDER) -> None:
        self._vault_root = vault_root.expanduser().resolve()
        self._notes_root = self._vault_root / notes_folder

    def upsert_note(self, note: ObsidianNote) -> WikiUpdateResult:
        """Create or update a generated note without overwriting user-written content."""

        self._ensure_folders()
        existing_note_path = self._find_existing_note(note)
        note_path = existing_note_path or self._available_note_path(note.filename)
        existed = note_path.exists()
        warnings: list[str] = []

        if existed:
            original = note_path.read_text(encoding="utf-8")
            updated_markdown, changed, update_warnings = _merge_generated_note(original, note)
            warnings.extend(update_warnings)
        else:
            updated_markdown = _new_managed_note(note)
            changed = True

        if changed:
            note_path.write_text(updated_markdown, encoding="utf-8")
            logger.info(
                "Wrote Obsidian note file.",
                extra={
                    "path": str(note_path),
                    "note_created": not existed,
                    "note_updated": existed,
                },
            )

        note_entries = self._collect_note_entries()
        index_path = self._update_index(note_entries)
        overview_path = self._update_overview(note_entries)
        log_path = self._append_log_entry(note=note, note_path=note_path, created=not existed)

        logger.info(
            "Wiki note upsert completed.",
            extra={
                "note_path": str(note_path),
                "note_created": not existed,
                "note_updated": changed and existed,
                "source": note.source,
            },
        )

        return WikiUpdateResult(
            note_path=note_path,
            created=not existed,
            updated=changed and existed,
            index_path=index_path,
            overview_path=overview_path,
            log_path=log_path,
            warnings=warnings,
        )

    def initialize(self) -> None:
        """Create vault folders and core wiki files when missing."""

        self._ensure_folders()
        note_entries = self._collect_note_entries()
        self._update_index(note_entries)
        self._update_overview(note_entries)
        self._ensure_file(self._vault_root / LOG_FILE, "# Log\n\n")

    def _ensure_folders(self) -> None:
        self._vault_root.mkdir(parents=True, exist_ok=True)
        self._notes_root.mkdir(parents=True, exist_ok=True)

    def _find_existing_note(self, note: ObsidianNote) -> Path | None:
        for path in self._notes_root.glob("*.md"):
            if _extract_frontmatter_source(path) == note.source:
                return path

        return None

    def _available_note_path(self, filename: str) -> Path:
        candidate = self._notes_root / filename
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix or ".md"
        counter = 2
        while True:
            numbered_candidate = self._notes_root / f"{stem} {counter}{suffix}"
            if not numbered_candidate.exists():
                return numbered_candidate
            counter += 1

    def _collect_note_entries(self) -> list[tuple[str, Path, str | None]]:
        entries: list[tuple[str, Path, str | None]] = []
        if not self._notes_root.exists():
            return entries

        for path in sorted(self._notes_root.glob("*.md"), key=lambda item: item.stem.lower()):
            title = _extract_frontmatter_value(path, "title") or path.stem
            source = _extract_frontmatter_source(path)
            entries.append((title, path, source))

        return entries

    def _update_index(self, note_entries: list[tuple[str, Path, str | None]]) -> Path:
        path = self._vault_root / INDEX_FILE
        body = "\n".join(f"- [[{entry[1].stem}|{entry[0]}]]" for entry in note_entries)
        managed = body or "- No generated notes yet."
        content = _upsert_managed_file(
            existing=_read_optional(path),
            title="Index",
            managed_content=managed,
        )
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote wiki index file.", extra={"path": str(path)})
        return path

    def _update_overview(self, note_entries: list[tuple[str, Path, str | None]]) -> Path:
        path = self._vault_root / OVERVIEW_FILE
        total = len(note_entries)
        sources = sorted({entry[2] for entry in note_entries if entry[2]})
        lines = [
            f"- Total generated notes: {total}",
            f"- Indexed sources: {len(sources)}",
            "- Core pages: [[index]], [[overview]], [[log]]",
            "",
            "## Recent Notes",
            "",
        ]
        lines.extend(f"- [[{entry[1].stem}|{entry[0]}]]" for entry in note_entries[-10:])
        if total == 0:
            lines.append("- No generated notes yet.")

        content = _upsert_managed_file(
            existing=_read_optional(path),
            title="Overview",
            managed_content="\n".join(lines),
        )
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote wiki overview file.", extra={"path": str(path)})
        return path

    def _append_log_entry(self, *, note: ObsidianNote, note_path: Path, created: bool) -> Path:
        path = self._vault_root / LOG_FILE
        self._ensure_file(path, "# Log\n\n")
        timestamp = datetime.now(tz=UTC).isoformat()
        action = "created" if created else "updated"
        entry = f"- {timestamp} - {action} [[{note_path.stem}|{note.title}]] from {note.source}\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        logger.info("Appended wiki log entry.", extra={"path": str(path), "action": action})
        return path

    @staticmethod
    def _ensure_file(path: Path, default_content: str) -> None:
        if not path.exists():
            path.write_text(default_content, encoding="utf-8")
            logger.info("Created wiki support file.", extra={"path": str(path)})


def _new_managed_note(note: ObsidianNote) -> str:
    frontmatter, body = _split_frontmatter(note.markdown)
    managed_body = _with_navigation(body.strip())
    return f"{frontmatter}{MANAGED_BEGIN}\n{managed_body}\n{MANAGED_END}\n"


def _merge_generated_note(existing: str, note: ObsidianNote) -> tuple[str, bool, list[str]]:
    warnings: list[str] = []
    _frontmatter, generated_body = _split_frontmatter(note.markdown)
    managed_body = _with_navigation(generated_body.strip())
    managed_block = f"{MANAGED_BEGIN}\n{managed_body}\n{MANAGED_END}"

    if MANAGED_BEGIN in existing and MANAGED_END in existing:
        start = existing.index(MANAGED_BEGIN)
        end = existing.index(MANAGED_END, start) + len(MANAGED_END)
        updated = f"{existing[:start]}{managed_block}{existing[end:]}"
        return updated, updated != existing, warnings

    warnings.append(
        "Existing note had no managed block, so generated content was appended "
        "instead of replacing content."
    )
    separator = "\n\n" if existing.strip() else ""
    updated = f"{existing.rstrip()}{separator}{managed_block}\n"
    return updated, updated != existing, warnings


def _with_navigation(body: str) -> str:
    navigation = "\n".join(
        [
            "## Wiki Navigation",
            "",
            "- [[index]]",
            "- [[overview]]",
            "- [[log]]",
        ]
    )
    return f"{body}\n\n{navigation}".strip()


def _split_frontmatter(markdown: str) -> tuple[str, str]:
    match = _FRONTMATTER_PATTERN.match(markdown)
    if match is None:
        return "", markdown.strip()
    return markdown[: match.end()], markdown[match.end() :].strip()


def _upsert_managed_file(*, existing: str | None, title: str, managed_content: str) -> str:
    managed_block = f"{MANAGED_BEGIN}\n{managed_content.strip()}\n{MANAGED_END}\n"
    if existing is None:
        return f"# {title}\n\n{managed_block}"

    if MANAGED_BEGIN in existing and MANAGED_END in existing:
        start = existing.index(MANAGED_BEGIN)
        end = existing.index(MANAGED_END, start) + len(MANAGED_END)
        return f"{existing[:start]}{managed_block.rstrip()}{existing[end:]}"

    return f"{existing.rstrip()}\n\n{managed_block}"


def _extract_frontmatter_source(path: Path) -> str | None:
    return _extract_frontmatter_value(path, "source")


def _extract_frontmatter_value(path: Path, key: str) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        return None

    pattern = re.compile(rf"^{re.escape(key)}:\s*[\"']?(?P<value>.+?)[\"']?\s*$", re.MULTILINE)
    value_match = pattern.search(match.group("frontmatter"))
    if value_match is None:
        return None
    return _unescape_frontmatter_value(value_match.group("value").strip())


def _unescape_frontmatter_value(value: str) -> str:
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _read_optional(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
