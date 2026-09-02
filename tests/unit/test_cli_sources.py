"""Tests for the ``pam sources`` command and its source-listing helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from app.cli import entry
from app.infrastructure.state.manifest import ManifestManager

runner = CliRunner()


def _write_vector_store(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"entries": entries}),
        encoding="utf-8",
    )


def _entry(source: str, source_type: str, chunk_index: int = 0, **extra: object) -> dict:
    return {
        "id": f"{source}:{chunk_index}",
        "text": "chunk text",
        "embedding": [0.0, 1.0],
        "source": source,
        "source_type": source_type,
        "chunk_index": chunk_index,
        "start_char": 0,
        "end_char": 10,
        "metadata": {},
        **extra,
    }


def _settings(tmp_path: Path) -> Any:
    """Return a lightweight settings namespace pointing at tmp."""
    from types import SimpleNamespace

    return SimpleNamespace(
        paths=SimpleNamespace(
            manifest_root=tmp_path / "manifests",
            project_root=tmp_path,
        ),
        manifest=SimpleNamespace(
            path=tmp_path / "manifests" / "processed.json",
            enabled=True,
        ),
    )


class TestReadVectorStoreSources:
    def test_groups_and_sorts_sources(self, tmp_path: Path) -> None:
        store = tmp_path / "manifests" / "vector_store.json"
        _write_vector_store(
            store,
            [
                _entry("zeta.pdf", "pdf", 0),
                _entry("zeta.pdf", "pdf", 1),
                _entry("alpha.md", "markdown", 0),
            ],
        )

        rows = entry._read_vector_store_sources(_settings(tmp_path))

        assert rows is not None
        assert [r.source for r in rows] == ["alpha.md", "zeta.pdf"]
        assert rows[1].chunks == 2
        assert rows[0].type == "markdown"

    def test_empty_when_store_missing(self, tmp_path: Path) -> None:
        rows = entry._read_vector_store_sources(_settings(tmp_path))
        assert rows == []

    def test_none_when_store_unreadable(self, tmp_path: Path) -> None:
        store = tmp_path / "manifests" / "vector_store.json"
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("{ not json", encoding="utf-8")

        assert entry._read_vector_store_sources(_settings(tmp_path)) is None

    def test_none_when_entries_not_list(self, tmp_path: Path) -> None:
        store = tmp_path / "manifests" / "vector_store.json"
        _write_vector_store(store, [])
        store.write_text(json.dumps({"entries": {}}), encoding="utf-8")

        assert entry._read_vector_store_sources(_settings(tmp_path)) is None

    def test_type_defaults_from_first_entry(self, tmp_path: Path) -> None:
        store = tmp_path / "manifests" / "vector_store.json"
        _write_vector_store(
            store,
            [
                _entry("a.md", ""),
                _entry("a.md", "markdown", 1),
            ],
        )

        rows = entry._read_vector_store_sources(_settings(tmp_path))

        assert rows is not None
        assert rows[0].type == "markdown"


class TestAnnotateSourceLedger:
    def test_processed_status_and_last_ingested(self, tmp_path: Path) -> None:
        source = tmp_path / "notes.md"
        source.write_text("# Note", encoding="utf-8")
        leader = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
        entry_row = leader.add_processed_file(
            path=source,
            sha256="abc",
            extension=".md",
            status="processed",
        )

        row = entry.SourceRow(source=str(source), type="markdown")
        entry._annotate_source_ledger([row], leader, tmp_path)

        assert row.status == "processed"
        assert row.last_ingested == entry_row.processed_at

    def test_failed_takes_precedence(self, tmp_path: Path) -> None:
        source = tmp_path / "notes.md"
        source.write_text("# Note", encoding="utf-8")
        leader = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
        leader.add_processed_file(path=source, sha256="abc", extension=".md", status="failed")

        row = entry.SourceRow(source=str(source), type="markdown")
        entry._annotate_source_ledger([row], leader, tmp_path)

        assert row.status == "failed"

    def test_skipped_duplicate(self, tmp_path: Path) -> None:
        source = tmp_path / "notes.md"
        source.write_text("# Note", encoding="utf-8")
        leader = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
        leader.add_processed_file(
            path=source, sha256="abc", extension=".md", status="skipped_duplicate"
        )

        row = entry.SourceRow(source=str(source), type="markdown")
        entry._annotate_source_ledger([row], leader, tmp_path)

        assert row.status == "skipped_duplicate"

    def test_indexed_when_no_ledger_entry(self, tmp_path: Path) -> None:
        leader = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)

        row = entry.SourceRow(source=str(tmp_path / "orphan.pdf"), type="pdf")
        entry._annotate_source_ledger([row], leader, tmp_path)

        assert row.status == "indexed"
        assert row.last_ingested is None


class TestCliSources:
    def test_lists_indexed_sources(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        store = tmp_path / "manifests" / "vector_store.json"
        _write_vector_store(
            store,
            [
                _entry("zeta.pdf", "pdf", 0),
                _entry("zeta.pdf", "pdf", 1),
                _entry("alpha.md", "markdown", 0),
            ],
        )
        monkeypatch.setenv("PAM_PATHS__PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("PAM_PATHS__MANIFEST_ROOT", str(tmp_path / "manifests"))
        monkeypatch.setenv("PAM_MANIFEST__PATH", str(tmp_path / "manifests" / "processed.json"))

        result = runner.invoke(entry.cli, ["sources"])

        assert result.exit_code == 0
        assert "Indexed Sources" in result.output
        assert "alpha.md" in result.output
        assert "zeta.pdf" in result.output
        assert "markdown" in result.output
        assert "pdf" in result.output
        assert "2" in result.output

    def test_empty_state_message(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PAM_PATHS__PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("PAM_PATHS__MANIFEST_ROOT", str(tmp_path / "manifests"))
        monkeypatch.setenv("PAM_MANIFEST__PATH", str(tmp_path / "manifests" / "processed.json"))

        result = runner.invoke(entry.cli, ["sources"])

        assert result.exit_code == 0
        assert "No sources are indexed yet" in result.output

    def test_unavailable_store_exits_nonzero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        bad = tmp_path / "manifests" / "vector_store.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{ not json", encoding="utf-8")
        monkeypatch.setenv("PAM_PATHS__PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("PAM_PATHS__MANIFEST_ROOT", str(tmp_path / "manifests"))
        monkeypatch.setenv("PAM_MANIFEST__PATH", str(tmp_path / "manifests" / "processed.json"))

        result = runner.invoke(entry.cli, ["sources"])

        assert result.exit_code == 1
        assert "unavailable" in result.output.lower()
