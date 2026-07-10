"""Tests for the manifest manager."""

from __future__ import annotations

import json
from pathlib import Path

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
