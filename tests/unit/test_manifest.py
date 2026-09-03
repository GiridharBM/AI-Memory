"""Tests for the manifest manager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.infrastructure.state.manifest import ManifestManager


def test_manifest_creation(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"

    manager = ManifestManager(manifest_path, project_root=tmp_path)

    assert manifest_path.exists()
    assert manager.count() == 0


def test_manifest_loading_and_saving(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    digest = manager.hash_for_path(source)
    manager.add_processed_file(path=source, sha256=digest, extension=".md")
    manager.save()

    reloaded = ManifestManager(manifest_path, project_root=tmp_path)

    assert reloaded.count() == 1
    assert reloaded.contains_hash(digest)
    assert reloaded.contains_path(source)


def test_manifest_empty_state(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)

    assert manager.count() == 0
    assert manager.list_entries() == []


def test_manifest_corrupted_recovery(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{broken", encoding="utf-8")

    manager = ManifestManager(manifest_path, project_root=tmp_path)

    corrupted_path = manifest_path.with_name("processed_files.corrupted.json")
    assert corrupted_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {"version": 1, "files": []}
    assert manager.count() == 0


def test_loaded_flag_set_on_save_success(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)

    assert manager._loaded is True


def test_loaded_flag_not_set_on_save_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    seen: dict[str, bool] = {}

    def _failing_save(self: ManifestManager) -> None:
        seen["loaded"] = self._loaded
        raise OSError("disk full")

    monkeypatch.setattr(ManifestManager, "save", _failing_save)
    with pytest.raises(OSError):
        ManifestManager(manifest_path, project_root=tmp_path)

    assert seen["loaded"] is False


# ── Phase 6A: durable ingestion ledger ────────────────────────────────


def test_successful_hash_dedup_ignores_failed_entries(tmp_path: Path) -> None:
    """A failed entry must not block re-processing the same file (retry)."""
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    digest = manager.hash_for_path(source)

    assert not manager.contains_successful_hash(digest)

    manager.add_failed_file(path=source, sha256=digest, extension=".md", error_reason="boom")

    assert manager.contains_hash(digest)  # recorded in the ledger
    assert not manager.contains_successful_hash(digest)  # but not dedup-eligible


def test_ledger_outcome_fields_round_trip(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    digest = manager.hash_for_path(source)
    manager.add_processed_file(
        path=source,
        sha256=digest,
        extension=".md",
        status="failed",
        error_reason="EMBEDDING/INDEXING FAILURE: ollama down",
        chunks_stored=0,
        embedding_succeeded=False,
        indexing_succeeded=False,
    )
    manager.save()

    reloaded = ManifestManager(manifest_path, project_root=tmp_path)
    entry = reloaded.list_entries()[0]

    assert entry.status == "failed"
    assert entry.error_reason == "EMBEDDING/INDEXING FAILURE: ollama down"
    assert entry.chunks_stored == 0
    assert entry.embedding_succeeded is False
    assert entry.indexing_succeeded is False


def test_add_failed_file_records_durable_failure(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    digest = manager.hash_for_path(source)

    manager.add_failed_file(path=source, sha256=digest, extension=".md", error_reason="oops")

    assert manager.count() == 1
    entry = manager.list_entries()[0]
    assert entry.status == "failed"
    assert entry.error_reason == "oops"


def test_skipped_duplicate_records_ledger_entry(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    digest = manager.hash_for_path(source)

    manager.add_processed_file(
        path=source, sha256=digest, extension=".md", status="skipped_duplicate",
    )

    assert manager.contains_successful_hash(digest)
    assert manager.list_entries()[0].status == "skipped_duplicate"
