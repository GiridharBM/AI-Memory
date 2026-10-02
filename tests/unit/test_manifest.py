"""Tests for the manifest manager."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.infrastructure.state.manifest import (
    ManifestManager,
    historical_url_ledger_form,
    is_url_source,
    url_matches_ledger_entry,
)


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


# -- V1.1.1 D3: path-scoped dedup mirrors hash-scoped dedup ----------------
# A failed entry must not block a retry, so a previously failed path is only
# a duplicate once it carries a successful status.


def test_contains_successful_path_false_for_failed(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.xyz"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("blob", encoding="utf-8")

    manager.add_failed_file(path=source, sha256="", extension=".xyz", error_reason="oops")

    assert manager.contains_successful_path(source) is False
    # The pre-existing status-agnostic lookup is intentionally unchanged.
    assert manager.contains_path(source) is True


def test_contains_successful_path_true_for_processed(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.xyz"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("blob", encoding="utf-8")

    manager.add_processed_file(path=source, sha256="", extension=".xyz", status="processed")

    assert manager.contains_successful_path(source) is True


def test_contains_successful_path_true_for_skipped_duplicate(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.xyz"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("blob", encoding="utf-8")

    manager.add_processed_file(
        path=source, sha256="", extension=".xyz", status="skipped_duplicate",
    )

    assert manager.contains_successful_path(source) is True


def test_contains_successful_path_mirrors_hash_semantics_for_failed(tmp_path: Path) -> None:
    """A failed hashable source is retryable too: both lookups must agree."""
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)
    source = tmp_path / "data" / "inbox" / "notes.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    digest = manager.hash_for_path(source)

    manager.add_failed_file(path=source, sha256=digest, extension=".md", error_reason="oops")

    assert manager.contains_successful_hash(digest) is False
    assert manager.contains_successful_path(source) is False


def test_contains_successful_path_false_for_unknown_path(tmp_path: Path) -> None:
    manifest_path = tmp_path / "data" / "manifests" / "processed_files.json"
    manager = ManifestManager(manifest_path, project_root=tmp_path)

    assert manager.contains_successful_path(tmp_path / "never-seen.xyz") is False


# ── V1.1.1 D3-C: exact URLs are CWD-independent ──────────────────────────


def test_url_identity_uses_exact_submitted_string(tmp_path: Path) -> None:
    manager = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )
    url = "https://github.com/example/pam"

    manager.add_processed_file(path=url, sha256="", extension="")

    assert manager.list_entries()[0].original_path == url
    assert manager.contains_successful_url(url) is True


def test_url_variants_remain_distinct_identities(tmp_path: Path) -> None:
    manager = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )
    plain_url = "https://github.com/o/r"
    slashed_url = "https://github.com/o/r/"
    watch_url = "https://www.youtube.com/watch?v=ID"
    short_url = "https://youtu.be/ID"

    manager.add_processed_file(path=plain_url, sha256="", extension="")
    manager.add_processed_file(path=watch_url, sha256="", extension="")

    assert manager.contains_successful_url(plain_url) is True
    assert manager.contains_successful_url(slashed_url) is False
    assert manager.contains_successful_url(watch_url) is True
    assert manager.contains_successful_url(short_url) is False


def test_historical_cwd_mangled_url_matches_exact_url(tmp_path: Path) -> None:
    url = "https://github.com/example/pam"
    legacy_path = f"{tmp_path}{os.sep}https:{os.sep}github.com{os.sep}example{os.sep}pam"

    assert is_url_source(url) is True
    assert is_url_source(legacy_path) is False
    assert url_matches_ledger_entry(legacy_path, url) is True
    assert url_matches_ledger_entry(url, url) is True
    assert url_matches_ledger_entry(legacy_path, f"{url}/") is False


def test_absolute_local_path_identity_is_unchanged_across_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "manifests" / "processed.json"
    source = tmp_path / "notes" / "local.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Local", encoding="utf-8")
    other_directory = tmp_path / "elsewhere"
    other_directory.mkdir()

    manager = ManifestManager(manifest_path, project_root=tmp_path)
    manager.add_processed_file(path=source, sha256="local-digest", extension=".md")
    manager.save()
    before = manager.list_entries()[0].original_path

    monkeypatch.chdir(other_directory)
    reloaded = ManifestManager(manifest_path, project_root=tmp_path)

    assert reloaded.contains_successful_path(source) is True
    assert reloaded.list_entries()[0].original_path == before


def test_multiple_historical_url_attempts_match_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "manifests" / "processed.json"
    legacy_directory = tmp_path / "legacy-cwd"
    legacy_directory.mkdir()
    retry_directory = tmp_path / "retry-cwd"
    retry_directory.mkdir()
    url = "https://github.com/example/pam"
    manager = ManifestManager(manifest_path, project_root=tmp_path)

    monkeypatch.chdir(legacy_directory)
    manager.add_failed_file(
        path=Path(url), sha256="", extension="", error_reason="OSError: first"
    )
    manager.add_failed_file(
        path=Path(url), sha256="", extension="", error_reason="OSError: second"
    )
    manager.add_processed_file(path=Path(url), sha256="", extension="", status="processed")
    manager.save()
    before = [(entry.status, entry.original_path) for entry in manager.list_entries()]

    monkeypatch.chdir(retry_directory)
    reloaded = ManifestManager(manifest_path, project_root=tmp_path)

    assert reloaded.contains_successful_url(url) is True
    assert reloaded.count() == 3
    assert [(entry.status, entry.original_path) for entry in reloaded.list_entries()] == before


# ── V1.1.1 D3-C repair: URL rows vs historical rows vs local paths ─────────


def _legacy_row(cwd: Path, url: str) -> str:
    return str(Path(cwd) / Path(url))


def test_historical_row_matches_only_the_url_it_was_written_for(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy-cwd"
    legacy.mkdir()
    row = _legacy_row(legacy, "https://github.com/o/r")

    assert url_matches_ledger_entry(row, "https://github.com/o/r") is True
    assert url_matches_ledger_entry(row, "https://github.com/o/r/") is False
    assert url_matches_ledger_entry(row, "https://github.com/o/R") is False
    assert url_matches_ledger_entry(row, "https://github.com/o/r?x=1") is False
    assert url_matches_ledger_entry(row, "https://github.com/o/other") is False
    assert url_matches_ledger_entry(row, "https://gitlab.com/o/r") is False
    assert url_matches_ledger_entry(row, "https://github.com/o/r.git") is False


def test_trailing_slash_variants_produce_distinct_historical_forms(tmp_path: Path) -> None:
    plain = "https://github.com/o/r"
    slashed = f"{plain}/"
    legacy = tmp_path / "legacy-cwd"
    legacy.mkdir()
    base_row = _legacy_row(legacy, plain)

    # The legacy identity preserves the trailing slash: the two spellings
    # must never collapse into one another.
    assert historical_url_ledger_form(plain) != historical_url_ledger_form(slashed)
    assert historical_url_ledger_form(slashed).endswith("/")
    assert url_matches_ledger_entry(base_row, plain) is True
    assert url_matches_ledger_entry(base_row, slashed) is False

    # A historical row that keeps the trailing separator belongs to the
    # slashed spelling only. (The old writer dropped the slash, so only a
    # slash-preserving stored form can prove the matcher tells them apart.)
    slashed_row = f"{base_row}{os.sep}"
    assert url_matches_ledger_entry(slashed_row, slashed) is True
    assert url_matches_ledger_entry(slashed_row, plain) is False


def test_url_variant_spellings_stay_distinct(tmp_path: Path) -> None:
    base = "https://github.com/o/r"
    legacy = tmp_path / "legacy-cwd"
    legacy.mkdir()
    row = _legacy_row(legacy, base)

    for variant in (
        f"{base}/",
        f"{base}.git",
        f"{base}?x=1",
        f"{base}#x",
        "https://github.com/o/R",
        "https://gitlab.com/o/r",
        "https://www.youtube.com/watch?v=ABC",
        "https://youtu.be/ABC",
        "https://www.youtube.com/watch?v=ABC&t=30",
    ):
        assert url_matches_ledger_entry(row, variant) is False
        assert url_matches_ledger_entry(variant, variant) is True
    assert url_matches_ledger_entry(row, base) is True


def test_historical_row_matches_both_separator_spellings(tmp_path: Path) -> None:
    url = "https://github.com/o/r"
    windows_spelling = f"{tmp_path}{os.sep}https:{os.sep}github.com{os.sep}o{os.sep}r"
    posix_spelling = f"{tmp_path.as_posix()}/https:/github.com/o/r"

    assert url_matches_ledger_entry(windows_spelling, url) is True
    assert url_matches_ledger_entry(posix_spelling, url) is True


def test_nested_scheme_path_is_not_a_historical_url_row(tmp_path: Path) -> None:
    inner_url = "https://github.com/o/r"
    nested_url = "https://x/a/https://github.com/o/r"
    nested = f"{tmp_path.as_posix()}/https:/x/a/https:/github.com/o/r"

    assert url_matches_ledger_entry(nested, inner_url) is False
    assert url_matches_ledger_entry(nested, nested_url) is True


def test_real_local_file_under_url_shaped_path_is_not_a_url_row(tmp_path: Path) -> None:
    url = "https://github.com/o/r"
    local = Path(f"{tmp_path.as_posix()}/https:/github.com/o/r")
    try:
        local.parent.mkdir(parents=True, exist_ok=True)
    except OSError:  # Windows forbids a "https:" path component.
        pytest.skip("platform forbids URL-shaped directory names")
    local.write_text("not a url", encoding="utf-8")

    assert url_matches_ledger_entry(str(local), url) is False
    assert url_matches_ledger_entry(str(local), url, tmp_path) is False
    assert url_matches_ledger_entry(str(local.parent / "sibling.md"), url, tmp_path) is False
    # The file must also survive as an ordinary local ledger row.
    manager = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
    manager.add_processed_file(path=local, sha256="localdigest", extension="")
    assert manager.contains_path(local) is True
    assert manager.contains_successful_url(url) is False


def test_exact_row_does_not_hide_a_historical_row(tmp_path: Path) -> None:
    url = "https://github.com/o/r"
    legacy = tmp_path / "legacy-cwd"
    legacy.mkdir()
    row = _legacy_row(legacy, url)
    manager = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
    manager.add_processed_file(path=url, sha256="", extension="")
    manager.add_processed_file(path=row, sha256="", extension="")

    assert manager.count() == 2
    assert manager.contains_successful_url(url) is True
    assert all(
        url_matches_ledger_entry(entry.original_path, url) for entry in manager.list_entries()
    )


def test_url_identity_ignores_surrounding_whitespace(tmp_path: Path) -> None:
    manager = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
    padded = "  https://github.com/o/r  "

    manager.add_processed_file(path=padded, sha256="", extension="")

    assert manager.list_entries()[0].original_path == "https://github.com/o/r"
    assert manager.contains_successful_url("https://github.com/o/r") is True


def test_remove_entry_deletes_exact_url_row_and_leaves_local_rows(tmp_path: Path) -> None:
    manager = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# Local", encoding="utf-8")
    manager.add_processed_file(path="https://github.com/o/r", sha256="", extension="")
    manager.add_processed_file(path=source, sha256="d", extension=".md")

    manager.remove_entry(path="https://github.com/o/r")

    assert manager.count() == 1
    assert manager.contains_successful_url("https://github.com/o/r") is False
    assert manager.contains_successful_path(source) is True


def test_remove_entry_does_not_guess_a_url_from_a_mangled_path(tmp_path: Path) -> None:
    manager = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
    manager.add_processed_file(path="https://github.com/o/r", sha256="", extension="")

    # Path("https://github.com/o/r") loses the "://" that defines URL identity;
    # refusing to guess is safer than deleting the wrong row. CLI removal of a
    # historical row goes through url_matches_ledger_entry instead.
    manager.remove_entry(path=Path("https:/github.com/o/r"))

    assert manager.count() == 1
    assert manager.contains_successful_url("https://github.com/o/r") is True
