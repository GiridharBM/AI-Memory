"""Phase V1.1-A4 tests: ``pam remove`` source management hardening.

Verifies source-scoped, deterministic deletion: only the requested source's
vector chunks, knowledge-graph nodes/edges, and ledger entries are removed,
identical-SHA siblings survive, BM25 rebuilds on version bump, and the CLI
reports not-found / ambiguous / partial-failure truthfully with non-zero exits.
Uses isolated temporary stores only (never touches the real corpus).

Coverage map (A4 STEP 11 matrix): remove one source, unrelated survives,
multiple chunks, KG nodes/edges, ledger cleanup, BM25 invalidation,
persistence after reload, nonexistent source, normalized path, relative path,
URL, identical-SHA different paths, remove-then-re-ingest, ambiguous source,
partial failure, CLI output, exit codes, no secret leakage, no traceback,
idempotent repeated remove.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from app.cli import entry
from app.domain.knowledge_graph import KnowledgeEdge, KnowledgeGraph, KnowledgeNode
from app.domain.semantic_chunking import DocumentChunk
from app.infrastructure.state.hashing import compute_file_hash
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vector_store import VectorStore

runner = CliRunner()


def _settings(tmp_path: Path) -> Any:
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


def _invoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
) -> Any:
    monkeypatch.setattr(entry, "_load_configured_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(entry, "setup_logging", lambda _settings: None)
    return runner.invoke(entry.cli, ["remove", *args])


def _write_file(tmp_path: Path, rel: str, content: str = "content") -> Path:
    source = tmp_path / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _write_vector_store(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def _chunk_entry(source: str, index: int) -> dict:
    return {
        "id": f"{source}:{index}",
        "text": f"unique lexical term for {source} chunk {index}",
        "embedding": [0.0, 1.0],
        "source": source,
        "source_type": "markdown",
        "chunk_index": index,
        "start_char": 0,
        "end_char": 10,
        "metadata": {},
    }


def _seed(
    tmp_path: Path,
    sources: list[str],
    *,
    sha256: str | None = None,
    ledger_ordered: list[str] | None = None,
) -> None:
    """Seed vector store, KG, and ledger for the given absolute source paths."""
    _write_vector_store(
        tmp_path / "manifests" / "vector_store.json",
        [c for s in sources for c in (_chunk_entry(s, 0), _chunk_entry(s, 1))],
    )
    g = KnowledgeGraph()
    for s in sources:
        g.add_node(KnowledgeNode(id=f"{s}::n1", label="N1", node_type="concept", source=s))
        g.add_node(KnowledgeNode(id=f"{s}::n2", label="N2", node_type="concept", source=s))
    g.save(tmp_path / "manifests" / "knowledge_graph.json")

    manifest = ManifestManager(
        tmp_path / "manifests" / "processed.json",
        project_root=tmp_path,
    )
    for source in ledger_ordered or sources:
        if sha256 is not None:
            digest = sha256
        else:
            try:
                digest = compute_file_hash(Path(source))
            except ValueError:
                digest = ""
        manifest.add_processed_file(
            path=Path(source),
            sha256=digest,
            extension=Path(source).suffix,
            status="processed",
            chunks_stored=2,
        )
    manifest.save()


def _reload(tmp_path: Path) -> tuple[VectorStore, KnowledgeGraph, ManifestManager]:
    store = VectorStore(persistence_path=tmp_path / "manifests" / "vector_store.json")
    kg = KnowledgeGraph.load(tmp_path / "manifests" / "knowledge_graph.json")
    manifest = ManifestManager(
        tmp_path / "manifests" / "processed.json",
        project_root=tmp_path,
    )
    return store, kg, manifest


def _seed_url(tmp_path: Path, url: str, *, ledger_row: str | None = None) -> None:
    """Seed a URL source the way the real URL ingestor stores it.

    Vector/KG key by the verbatim URL. Since D3-C the ledger row is the exact
    URL; pass ``ledger_row`` to reproduce a pre-D3-C CWD-mangled row. The row
    is written directly rather than through ``add_processed_file`` because that
    helper re-normalizes against the CWD.
    """
    _write_vector_store(
        tmp_path / "manifests" / "vector_store.json",
        [_chunk_entry(url, 0), _chunk_entry(url, 1)],
    )
    g = KnowledgeGraph()
    g.add_node(KnowledgeNode(id=f"{url}::n1", label="N1", node_type="concept", source=url))
    g.save(tmp_path / "manifests" / "knowledge_graph.json")

    row = {
        "sha256": "",
        "original_filename": Path(url).name,
        "original_path": url if ledger_row is None else ledger_row,
        "processed_at": "2026-09-01T00:00:00Z",
        "extension": ".md",
        "status": "processed",
        "generated_note": None,
    }
    mp = tmp_path / "manifests" / "processed.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    if mp.exists():
        data = json.loads(mp.read_text(encoding="utf-8"))
        data["files"].append(row)
    else:
        data = {"version": 1, "files": [row]}
    mp.write_text(json.dumps(data), encoding="utf-8")


def _sources_of(store: VectorStore) -> set[str]:
    return {e.source for e in store.entries()}


def _ledger_paths(manifest: ManifestManager) -> set[str]:
    return {e.original_path.replace("\\", "/") for e in manifest.list_entries()}


# ── Success paths ──────────────────────────────────────────────────────────


def test_remove_one_source_and_unrelated_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _write_file(tmp_path, "notes/a.md")
    b = _write_file(tmp_path, "notes/b.md")
    _seed(tmp_path, [str(a.resolve()), str(b.resolve())])

    result = _invoke(tmp_path, monkeypatch, str(a.resolve()))

    assert result.exit_code == 0, result.output
    assert "Source Removed" in result.output
    assert "Vector chunks removed" in result.output
    # Seeded source carried exactly 2 chunks: assert the reported removal
    # count itself instead of scanning raw output for "0", which also matches
    # unrelated logging timestamps/paths under full-suite runs.
    chunks_match = re.search(r"Vector chunks removed\D*(\d+)", result.output)
    assert chunks_match is not None, result.output
    assert int(chunks_match.group(1)) == 2, result.output
    store, kg, manifest = _reload(tmp_path)
    assert _sources_of(store) == {str(b.resolve())}
    assert {n.source for n in kg.nodes.values()} == {str(b.resolve())}
    assert _ledger_paths(manifest) == {"notes/b.md"}


def test_remove_multiple_chunks_all_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _write_file(tmp_path, "big.md")
    _write_vector_store(
        tmp_path / "manifests" / "vector_store.json",
        [_chunk_entry(str(a.resolve()), i) for i in range(3)],
    )
    g = KnowledgeGraph()
    g.add_node(
        KnowledgeNode(id=str(a.resolve()), label="X", node_type="concept", source=str(a.resolve()))
    )
    g.save(tmp_path / "manifests" / "knowledge_graph.json")
    manifest = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )
    manifest.add_processed_file(path=a, sha256="x", extension=".md", status="processed")
    manifest.save()

    result = _invoke(tmp_path, monkeypatch, str(a.resolve()))

    assert result.exit_code == 0
    store, _kg, _manifest = _reload(tmp_path)
    assert store.entries() == []


def test_remove_kg_nodes_and_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _write_file(tmp_path, "a.md")
    path = str(a.resolve())
    _write_vector_store(tmp_path / "manifests" / "vector_store.json", [_chunk_entry(path, 0)])
    g = KnowledgeGraph()
    g.add_node(KnowledgeNode(id="n1", label="X", node_type="concept", source=path))
    g.add_node(KnowledgeNode(id="n2", label="Y", node_type="concept", source=path))
    g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
    g.save(tmp_path / "manifests" / "knowledge_graph.json")
    manifest = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )
    manifest.add_processed_file(path=a, sha256="x", extension=".md", status="processed")
    manifest.save()

    result = _invoke(tmp_path, monkeypatch, path)

    assert result.exit_code == 0
    assert "KG nodes removed" in result.output
    store, kg, manifest = _reload(tmp_path)
    assert store.entries() == []
    assert kg.edges == []
    assert kg.nodes == {}


def test_remove_persists_after_reload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _write_file(tmp_path, "a.md")
    b = _write_file(tmp_path, "b.md")
    _seed(tmp_path, [str(a.resolve()), str(b.resolve())])
    result = _invoke(tmp_path, monkeypatch, str(a.resolve()))
    assert result.exit_code == 0
    store, _kg, _manifest = _reload(tmp_path)
    # second reload proves the on-disk file (not just in-memory) state
    store2 = VectorStore(persistence_path=tmp_path / "manifests" / "vector_store.json")
    assert _sources_of(store2) == {str(b.resolve())}


# ── URL and path forms ─────────────────────────────────────────────────────


def test_remove_url_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://github.com/example/repo"
    _seed_url(tmp_path, url)
    result = _invoke(tmp_path, monkeypatch, url)
    assert result.exit_code == 0, result.output
    store, kg, manifest = _reload(tmp_path)
    assert store.entries() == []
    assert kg.nodes == {}
    assert manifest.list_entries() == []


def test_remove_deletes_exact_url_row_and_its_vectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://github.com/example/pam"
    _seed_url(tmp_path, url)

    assert json.loads((tmp_path / "manifests" / "processed.json").read_text(encoding="utf-8"))[
        "files"
    ][0]["original_path"] == url
    result = _invoke(tmp_path, monkeypatch, url)

    assert result.exit_code == 0, result.output
    store, kg, manifest = _reload(tmp_path)
    assert store.entries() == []
    assert kg.nodes == {}
    assert manifest.list_entries() == []
    assert manifest.contains_successful_url(url) is False


def test_remove_deletes_exact_and_historical_rows_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://github.com/example/pam"
    historical = str(Path(url))
    _seed_url(tmp_path, url)
    _seed_url(tmp_path, url, ledger_row=historical)
    _write_vector_store(
        tmp_path / "manifests" / "vector_store.json",
        [_chunk_entry(url, 0), _chunk_entry(url, 1)],
    )

    result = _invoke(tmp_path, monkeypatch, url)

    assert result.exit_code == 0, result.output
    store, _kg, manifest = _reload(tmp_path)
    assert store.entries() == []
    assert manifest.list_entries() == []


def test_remove_keeps_distinct_url_variant_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://github.com/o/r"
    slashed = f"{url}/"
    historical = str(Path(url))
    _seed_url(tmp_path, slashed, ledger_row=historical)
    _seed_url(tmp_path, slashed, ledger_row=slashed)
    _write_vector_store(
        tmp_path / "manifests" / "vector_store.json",
        [_chunk_entry(url, 0), _chunk_entry(slashed, 0)],
    )

    result = _invoke(tmp_path, monkeypatch, url)

    assert result.exit_code == 0, result.output
    store, _kg, manifest = _reload(tmp_path)
    # The base historical row genuinely belongs to the removed URL, so it is
    # removed with it. The slashed variant is a different identity: its exact
    # row and its vectors survive.
    assert _sources_of(store) == {slashed}
    assert {entry.original_path for entry in manifest.list_entries()} == {slashed}


def test_remove_keeps_local_file_row_shaped_like_a_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://github.com/o/r"
    local = Path(f"{tmp_path.as_posix()}/https:/github.com/o/r")
    try:
        local.parent.mkdir(parents=True, exist_ok=True)
    except OSError:  # Windows forbids a "https:" path component.
        pytest.skip("platform forbids URL-shaped directory names")
    local.write_text("not a url", encoding="utf-8")
    manager = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )
    manager.add_processed_file(
        path=local, sha256="localdigest", extension="", status="processed"
    )
    manager.save()
    local_row = manager.list_entries()[0].original_path
    _seed_url(tmp_path, url)

    result = _invoke(tmp_path, monkeypatch, url)

    assert result.exit_code == 0, result.output
    _store, _kg, manifest = _reload(tmp_path)
    # The local file's ledger row survives the URL removal untouched.
    assert [entry.original_path for entry in manifest.list_entries()] == [local_row]
    assert manifest.contains_path(local) is True
    assert manifest.contains_successful_url(url) is False


def test_failed_only_url_remove_across_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://github.com/example/pam"
    unrelated_url = "https://github.com/example/other"
    legacy_directory = tmp_path / "legacy-cwd"
    legacy_directory.mkdir()
    retry_directory = tmp_path / "retry-cwd"
    retry_directory.mkdir()
    manager = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )

    monkeypatch.chdir(legacy_directory)
    manager.add_failed_file(
        path=Path(url), sha256="", extension="", error_reason="OSError: old failure"
    )
    manager.add_failed_file(
        path=Path(unrelated_url),
        sha256="",
        extension="",
        error_reason="OSError: unrelated",
    )
    manager.save()
    before = [entry.original_path for entry in manager.list_entries()]

    monkeypatch.chdir(retry_directory)
    result = _invoke(tmp_path, monkeypatch, url)

    assert result.exit_code == 0, result.output
    remaining = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    ).list_entries()
    assert [entry.original_path for entry in remaining] == [before[1]]
    assert remaining[0].error_reason == "OSError: unrelated"


def test_remove_exact_url_from_another_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://github.com/example/pam"
    _seed_url(tmp_path, url)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    monkeypatch.chdir(elsewhere)
    result = _invoke(tmp_path, monkeypatch, url)

    assert result.exit_code == 0, result.output
    store, kg, manifest = _reload(tmp_path)
    assert store.entries() == []
    assert kg.nodes == {}
    assert manifest.list_entries() == []
    assert manifest.contains_successful_url(url) is False


def test_remove_exact_and_historical_rows_from_another_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exact + historical rows for one URL coexist until removed together.

    Row 1 is a historical failed attempt written from another CWD; row 2 is
    the exact processed row. Neither is rewritten or merged, D4 still counts
    two attempts, and removing the URL deletes both rows but nothing else.
    """
    url = "https://github.com/example/pam"
    unrelated_url = "https://github.com/example/other"
    legacy_directory = tmp_path / "legacy-cwd"
    legacy_directory.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    manager = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )
    monkeypatch.chdir(legacy_directory)
    manager.add_failed_file(
        path=Path(url), sha256="", extension="", error_reason="OSError: old failure"
    )
    manager.save()
    historical_row = manager.list_entries()[0].original_path
    assert historical_row != url
    _seed_url(tmp_path, url)
    _seed_url(tmp_path, unrelated_url)
    _write_vector_store(
        tmp_path / "manifests" / "vector_store.json",
        [_chunk_entry(url, 0), _chunk_entry(unrelated_url, 0)],
    )
    reloaded = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )
    before = [entry.original_path for entry in reloaded.list_entries()]
    assert len(before) == 3  # D4: every attempt stays a row.

    monkeypatch.chdir(elsewhere)
    result = _invoke(tmp_path, monkeypatch, url)

    assert result.exit_code == 0, result.output
    remaining = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    ).list_entries()
    assert [entry.original_path for entry in remaining] == [unrelated_url]
    assert before[0] == historical_row  # historical evidence untouched in place
    store, _kg, _manifest = _reload(tmp_path)
    assert _sources_of(store) == {unrelated_url}


def test_remove_nested_scheme_history_not_matched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner_url = "https://github.com/o/r"
    nested_row = f"{tmp_path.as_posix()}/https:/x/a/https:/github.com/o/r"
    manager = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    )
    manager.add_failed_file(
        path=nested_row, sha256="", extension="", error_reason="OSError: nested"
    )
    manager.save()
    stored_row = manager.list_entries()[0].original_path

    result = _invoke(tmp_path, monkeypatch, inner_url)

    assert result.exit_code == 1, result.output
    assert "Source not found" in result.output
    remaining = ManifestManager(
        tmp_path / "manifests" / "processed.json", project_root=tmp_path
    ).list_entries()
    assert [entry.original_path for entry in remaining] == [stored_row]


def test_remove_padded_url_addresses_stripped_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://github.com/o/r"
    _seed_url(tmp_path, url)

    result = _invoke(tmp_path, monkeypatch, f"  {url}  ")

    assert result.exit_code == 0, result.output
    store, _kg, manifest = _reload(tmp_path)
    assert store.entries() == []
    assert manifest.list_entries() == []


def test_remove_relative_path_from_any_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _write_file(tmp_path, "notes/a.md")
    _seed(tmp_path, [str(a.resolve())])
    result = _invoke(tmp_path, monkeypatch, "notes/a.md")
    assert result.exit_code == 0, result.output
    store, _kg, manifest = _reload(tmp_path)
    assert store.entries() == []
    assert manifest.list_entries() == []


def test_remove_duplicated_absolute_vs_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _write_file(tmp_path, "a.md")
    _seed(tmp_path, [str(a.resolve())])
    result = _invoke(tmp_path, monkeypatch, str(a.resolve()))
    assert result.exit_code == 0


# ── Identical SHA but different paths (STEP 4) ─────────────────────────────


def test_identical_sha_removal_keeps_sibling_ledger_and_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _write_file(tmp_path, "one.md", content="identical content")
    b = _write_file(tmp_path, "two.md", content="identical content")
    digest = compute_file_hash(a)
    assert compute_file_hash(b) == digest
    # Two identical-content sources are only both present when the hash gate
    # was bypassed (e.g. manifest disabled). Ledger rows are seeded in the
    # reversed order so a content-hash-based removal would hit B's row first.
    _seed(
        tmp_path,
        [str(a.resolve()), str(b.resolve())],
        sha256=digest,
        ledger_ordered=[str(b.resolve()), str(a.resolve())],
    )

    result = _invoke(tmp_path, monkeypatch, str(a.resolve()))

    assert result.exit_code == 0, result.output
    store, kg, manifest = _reload(tmp_path)
    assert _sources_of(store) == {str(b.resolve())}
    assert {n.source for n in kg.nodes.values()} == {str(b.resolve())}
    assert _ledger_paths(manifest) == {"two.md"}


# ── Error behavior (STEP 5/10) ─────────────────────────────────────────────


def test_remove_nonexistent_exit_one_and_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _invoke(tmp_path, monkeypatch, str(tmp_path / "missing.md"))
    assert result.exit_code == 1
    assert "Source not found" in result.output
    assert "Traceback" not in result.output


def test_remove_ambiguous_aborts_without_deleting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _write_file(tmp_path, "dir1/a.md")
    b = _write_file(tmp_path, "dir2/a.md")
    _seed(tmp_path, [str(a.resolve()), str(b.resolve())])

    result = _invoke(tmp_path, monkeypatch, "a.md")

    assert result.exit_code == 1, result.output
    assert "ambiguous" in result.output.lower()
    assert "Traceback" not in result.output
    store, kg, manifest = _reload(tmp_path)
    assert _sources_of(store) == {str(a.resolve()), str(b.resolve())}
    assert {n.source for n in kg.nodes.values()} == {str(a.resolve()), str(b.resolve())}
    assert _ledger_paths(manifest) == {"dir1/a.md", "dir2/a.md"}


def test_remove_ambiguous_url_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_url(tmp_path, "https://github.com/one/repo")
    _seed_url(tmp_path, "https://github.com/two/repo")
    result = _invoke(tmp_path, monkeypatch, "repo")
    assert result.exit_code == 1
    assert "ambiguous" in result.output.lower()


def test_remove_partial_failure_knowledge_graph_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _write_file(tmp_path, "a.md")
    _seed(tmp_path, [str(a.resolve())])
    kg_path = tmp_path / "manifests" / "knowledge_graph.json"
    kg_path.write_text("{ this is not valid json", encoding="utf-8")

    result = _invoke(tmp_path, monkeypatch, str(a.resolve()))

    assert result.exit_code == 1, result.output
    assert "Remove failed" in result.output
    assert "Traceback" not in result.output
    store = VectorStore(persistence_path=tmp_path / "manifests" / "vector_store.json")
    manifest = ManifestManager(
        tmp_path / "manifests" / "processed.json",
        project_root=tmp_path,
    )
    assert _sources_of(store) == {str(a.resolve())}  # nothing deleted
    assert _ledger_paths(manifest) == {"a.md"}


def test_remove_corrupt_vector_store_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store that fails to load must not be replaced by an empty one."""
    a = _write_file(tmp_path, "a.md")
    _seed(tmp_path, [str(a.resolve())])
    store_path = tmp_path / "manifests" / "vector_store.json"
    store_path.write_text("{ this is not valid json", encoding="utf-8")
    corrupt = store_path.read_text(encoding="utf-8")

    result = _invoke(tmp_path, monkeypatch, str(a.resolve()))

    assert result.exit_code == 1, result.output
    assert "Remove failed" in result.output
    assert "Traceback" not in result.output
    # The corrupt bytes survive verbatim: no silent wipe to {"entries": []}.
    assert store_path.read_text(encoding="utf-8") == corrupt
    # The ledger is untouched too, so nothing was mutated on the way out.
    manifest = ManifestManager(
        tmp_path / "manifests" / "processed.json",
        project_root=tmp_path,
    )
    assert _ledger_paths(manifest) == {"a.md"}


def test_remove_idempotent_second_call_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _write_file(tmp_path, "a.md")
    _seed(tmp_path, [str(a.resolve())])
    first = _invoke(tmp_path, monkeypatch, str(a.resolve()))
    assert first.exit_code == 0
    second = _invoke(tmp_path, monkeypatch, str(a.resolve()))
    assert second.exit_code == 1
    assert "Source not found" in second.output
    assert "Traceback" not in second.output


# ── Re-ingest after remove (STEP 8) ────────────────────────────────────────


def test_remove_then_reingest_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _write_file(tmp_path, "a.md")
    _seed(tmp_path, [str(a.resolve())])
    result = _invoke(tmp_path, monkeypatch, str(a.resolve()))
    assert result.exit_code == 0

    manifest = ManifestManager(tmp_path / "manifests" / "processed.json", project_root=tmp_path)
    digest = compute_file_hash(a)
    assert manifest.contains_successful_hash(digest) is False
    assert manifest.contains_path(a) is False

    # A fresh workflow ingest stores chunks again (new source representation).
    from app.domain.documents import DocumentMetadata, SourceDocument
    from app.infrastructure.embeddings import EmbeddingResult
    from app.infrastructure.semantic_chunking import SemanticChunker
    from app.pipelines.ingest_workflow import IngestionWorkflow

    chunker = MagicMock(spec=SemanticChunker)
    chunk = DocumentChunk(
        chunk_id=f"{a.resolve()}::0", text="text", source=str(a.resolve()),
        source_type="markdown", chunk_index=0, start_char=0, end_char=4, metadata={},
    )
    chunker.chunk.return_value = [chunk]
    embedder = MagicMock()
    embedder.embed_batch.return_value = [EmbeddingResult(model="m", embedding=[0.1, 0.2])]
    wf = IngestionWorkflow(
        ingestion_service=MagicMock(), ollama_client=MagicMock(), note_generator=MagicMock(),
        writer=MagicMock(), chunker=chunker, embedding_service=embedder,
        vector_store=VectorStore(), knowledge_graph_builder=MagicMock(),
    )
    _kg, stored, _links = wf._run_knowledge_engine(
        SourceDocument(source=str(a.resolve()), filename="a.md", source_type="markdown",
                       text="text", metadata=DocumentMetadata()),
        MagicMock(),
    )
    assert stored == 1


# ── BM25 invalidation (STEP 9) ─────────────────────────────────────────────


def test_remove_bumps_version_and_bm25_rebuilds_dropping_deleted_source(tmp_path: Path) -> None:
    from app.infrastructure.search import HybridSearch

    a = _write_file(tmp_path, "alpha.md")
    b = _write_file(tmp_path, "beta.md")
    path = tmp_path / "manifests" / "vector_store.json"
    _write_vector_store(
        path, [_chunk_entry(str(a.resolve()), 0), _chunk_entry(str(b.resolve()), 0)]
    )

    store = VectorStore(persistence_path=path)
    search = HybridSearch(store)
    _lexical = search._lexical()
    assert _lexical is not None
    _, ids_before = _lexical
    assert str(a.resolve()) in ids_before[0]
    version_before = store.version

    store.remove_by_source(str(a.resolve()))
    assert store.version == version_before + 1  # removal bumps the rebuild signal
    _lexical = search._lexical()
    assert _lexical is not None
    _index, ids_after = _lexical
    assert len(ids_after) == 1
    assert ids_after == [f"{str(b.resolve())}:0"]


# ── Security (STEP 15) ─────────────────────────────────────────────────────


def test_remove_never_reads_or_leaks_secret_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = _write_file(tmp_path, ".env", content="TOKEN=super-secret-value")
    _seed(tmp_path, [str(secret.resolve())], sha256="envsha")
    result = _invoke(tmp_path, monkeypatch, str(secret.resolve()))
    assert result.exit_code == 0
    assert "super-secret-value" not in result.output
    assert "TOKEN=" not in result.output
    store = VectorStore(persistence_path=tmp_path / "manifests" / "vector_store.json")
    assert store.entries() == []


def test_remove_output_is_clean_no_secret_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = _write_file(tmp_path, ".env", content="TOKEN=super-secret-value")
    result = _invoke(tmp_path, monkeypatch, str(secret.resolve()))
    assert result.exit_code == 1
    assert "super-secret-value" not in result.output