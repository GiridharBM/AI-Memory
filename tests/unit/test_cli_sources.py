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
        entry._annotate_source_ledger([row], leader.list_entries(), tmp_path)

        assert row.status == "processed"
        assert row.last_ingested == entry_row.processed_at

    def test_failed_takes_precedence(self, tmp_path: Path) -> None:
        source = tmp_path / "notes.md"
        source.write_text("# Note", encoding="utf-8")
        leader = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
        leader.add_processed_file(path=source, sha256="abc", extension=".md", status="failed")

        row = entry.SourceRow(source=str(source), type="markdown")
        entry._annotate_source_ledger([row], leader.list_entries(), tmp_path)

        assert row.status == "failed"

    def test_skipped_duplicate(self, tmp_path: Path) -> None:
        source = tmp_path / "notes.md"
        source.write_text("# Note", encoding="utf-8")
        leader = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
        leader.add_processed_file(
            path=source, sha256="abc", extension=".md", status="skipped_duplicate"
        )

        row = entry.SourceRow(source=str(source), type="markdown")
        entry._annotate_source_ledger([row], leader.list_entries(), tmp_path)

        assert row.status == "skipped_duplicate"

    def test_indexed_when_no_ledger_entry(self, tmp_path: Path) -> None:
        leader = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)

        row = entry.SourceRow(source=str(tmp_path / "orphan.pdf"), type="pdf")
        entry._annotate_source_ledger([row], leader.list_entries(), tmp_path)

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

    def test_does_not_modify_corrupt_ledger(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A read must not quarantine or recreate a corrupt manifest."""
        _write_vector_store(
            tmp_path / "manifests" / "vector_store.json",
            [_entry("alpha.md", "markdown", 0)],
        )
        mp = tmp_path / "manifests" / "processed.json"
        mp.write_text("{ corrupt", encoding="utf-8")
        monkeypatch.setenv("PAM_PATHS__PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("PAM_PATHS__MANIFEST_ROOT", str(tmp_path / "manifests"))
        monkeypatch.setenv("PAM_MANIFEST__PATH", str(mp))

        result = runner.invoke(entry.cli, ["sources"])

        assert result.exit_code == 1
        assert "unavailable" in result.output.lower()
        assert "Traceback" not in result.output
        # Bytes survive: no quarantine, no fresh empty manifest, no rename.
        assert mp.read_text(encoding="utf-8") == "{ corrupt"
        assert [p.name for p in mp.parent.glob("processed.json*")] == ["processed.json"]

    def test_does_not_create_missing_ledger(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """An absent manifest is an empty ledger, not a file to be created."""
        _write_vector_store(
            tmp_path / "manifests" / "vector_store.json",
            [_entry("alpha.md", "markdown", 0)],
        )
        mp = tmp_path / "manifests" / "processed.json"
        monkeypatch.setenv("PAM_PATHS__PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("PAM_PATHS__MANIFEST_ROOT", str(tmp_path / "manifests"))
        monkeypatch.setenv("PAM_MANIFEST__PATH", str(mp))

        result = runner.invoke(entry.cli, ["sources"])

        assert result.exit_code == 0
        assert "alpha.md" in result.output
        assert not mp.exists()


class TestCliSourcesFailed:
    """D3-A: ``pam sources --failed`` is ledger-driven and claims no indexing."""

    @staticmethod
    def _failed_ledger(tmp_path: Path) -> ManifestManager:
        return ManifestManager(
            tmp_path / "manifests" / "processed.json", project_root=tmp_path
        )

    @staticmethod
    def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Point the CLI at tmp and widen the table so long cells stay intact."""

        monkeypatch.setenv("PAM_PATHS__PROJECT_ROOT", str(tmp_path))
        monkeypatch.setenv("PAM_PATHS__MANIFEST_ROOT", str(tmp_path / "manifests"))
        monkeypatch.setenv("PAM_MANIFEST__PATH", str(tmp_path / "manifests" / "processed.json"))
        monkeypatch.setenv("COLUMNS", "220")

    def test_default_listing_omits_failed_only_source(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The default listing stays vector-store authoritative (unchanged)."""
        _write_vector_store(
            tmp_path / "manifests" / "vector_store.json",
            [_entry("indexed.md", "markdown", 0)],
        )
        failed = tmp_path / "broken.md"
        manager = self._failed_ledger(tmp_path)
        manager.add_failed_file(
            path=failed, sha256="deadbeef", extension=".md", error_reason="RuntimeError: boom"
        )
        manager.save()
        self._env(monkeypatch, tmp_path)

        result = runner.invoke(entry.cli, ["sources"])

        assert result.exit_code == 0
        assert "Indexed Sources" in result.output
        assert "indexed.md" in result.output
        # The failed-only source is neither listed nor announced.
        assert "broken.md" not in result.output
        assert "Failed Sources" not in result.output

    def test_failed_only_local_source_listed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        failed = tmp_path / "broken.md"
        failed.write_text("# broken", encoding="utf-8")
        manager = self._failed_ledger(tmp_path)
        manager.add_failed_file(
            path=failed,
            sha256="deadbeef",
            extension=".md",
            error_reason="RuntimeError: embedding backend down",
        )
        manager.save()
        self._env(monkeypatch, tmp_path)

        result = runner.invoke(entry.cli, ["sources", "--failed"])

        assert result.exit_code == 0
        out = result.output
        assert "Failed Sources (not indexed)" in out
        assert "broken.md" in out
        assert ".md" in out
        assert "embedding backend down" in out
        # Never presented as an indexed row.
        assert "Indexed Sources" not in out
        assert "Chunks" not in out

    def test_failed_only_url_listed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        url = "https://github.com/example/pam/blob/main/README.md"
        manager = self._failed_ledger(tmp_path)
        row = manager.add_failed_file(
            path=Path(url), sha256="", extension="", error_reason="OSError: host unreachable"
        )
        manager.save()
        self._env(monkeypatch, tmp_path)

        result = runner.invoke(entry.cli, ["sources", "--failed"])

        assert result.exit_code == 0
        # The URL failure is shown under the identity the ledger recorded for it.
        assert row.original_path in result.output
        assert "host unreachable" in result.output

    def test_failed_unsupported_source_listed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        source = tmp_path / "weird.xyz"
        source.write_text("binary-ish", encoding="utf-8")
        manager = self._failed_ledger(tmp_path)
        manager.add_failed_file(
            path=source,
            sha256="",
            extension=".xyz",
            error_reason="IngestionWorkflowError: Unsupported source type",
        )
        manager.save()
        self._env(monkeypatch, tmp_path)

        result = runner.invoke(entry.cli, ["sources", "--failed"])

        assert result.exit_code == 0
        out = result.output
        assert "weird.xyz" in out
        assert ".xyz" in out
        assert "Unsupported source type" in out

    def test_repeated_failures_collapse_to_one_row_without_touching_history(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        source = tmp_path / "broken.md"
        source.write_text("# broken", encoding="utf-8")
        manager = self._failed_ledger(tmp_path)
        manager.add_failed_file(
            path=source, sha256="deadbeef", extension=".md", error_reason="RuntimeError: first"
        )
        manager.add_failed_file(
            path=source, sha256="deadbeef", extension=".md", error_reason="RuntimeError: second"
        )
        manager.save()
        self._env(monkeypatch, tmp_path)

        result = runner.invoke(entry.cli, ["sources", "--failed"])

        assert result.exit_code == 0
        out = result.output
        # One source row, with the attempt count surfaced rather than duplicated.
        assert out.count("broken.md") == 1
        assert "2" in out
        # Both underlying attempts survive: the ledger is append-only.
        after = ManifestManager(
            tmp_path / "manifests" / "processed.json", project_root=tmp_path
        )
        entries = after.list_entries()
        assert len(entries) == 2
        assert [e.error_reason for e in entries] == ["RuntimeError: first", "RuntimeError: second"]

    def test_empty_state_when_no_failures(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        source = tmp_path / "ok.md"
        source.write_text("# ok", encoding="utf-8")
        manager = self._failed_ledger(tmp_path)
        manager.add_processed_file(
            path=source, sha256="abc", extension=".md", status="processed"
        )
        manager.save()
        self._env(monkeypatch, tmp_path)

        result = runner.invoke(entry.cli, ["sources", "--failed"])

        assert result.exit_code == 0
        assert "No failed sources are recorded" in result.output
        assert "ok.md" not in result.output

    def test_does_not_create_or_modify_the_ledger(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Listing failures is read-only: no create, no quarantine, no rewrite."""
        mp = tmp_path / "manifests" / "processed.json"
        self._env(monkeypatch, tmp_path)

        result = runner.invoke(entry.cli, ["sources", "--failed"])

        assert result.exit_code == 0
        assert not mp.exists()

        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text("{ corrupt", encoding="utf-8")
        corrupt = runner.invoke(entry.cli, ["sources", "--failed"])

        assert corrupt.exit_code == 1
        assert "unavailable" in corrupt.output.lower()
        assert "Traceback" not in corrupt.output
        assert mp.read_text(encoding="utf-8") == "{ corrupt"
        assert [p.name for p in mp.parent.glob("processed.json*")] == ["processed.json"]

    def test_status_command_unchanged_by_failed_sources(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """D4 owns status counting: a failed entry still counts as before."""
        source = tmp_path / "broken.md"
        source.write_text("# broken", encoding="utf-8")
        manager = self._failed_ledger(tmp_path)
        manager.add_failed_file(
            path=source, sha256="deadbeef", extension=".md", error_reason="RuntimeError: boom"
        )
        manager.save()
        self._env(monkeypatch, tmp_path)

        result = runner.invoke(entry.cli, ["status"])

        assert result.exit_code == 0
        assert "Failed" in result.output
        assert "Failed Sources" not in result.output
