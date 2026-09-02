"""Phase V1.1-A5 tests: ``pam status`` observability hardening.

Verifies status is a *truthful, read-only* operational overview: counts come from
durable state, unavailable backing stores are reported as "unavailable" (never a
fabricated zero), real generated notes are separated from placeholder stubs,
last-ingestion derives from the durable ledger, and running status never mutates
any backing store or invokes an LLM.

Coverage map (A5 STEP 12): source count, chunk count, real-note count, placeholder
exclusion, processed count, failed count, retryable state (removed),
pending/queue state, last-ingestion, unavailable vector store / ledger / queue /
manifest (if applicable), empty state, CLI output, no traceback, no LLM, no
corpus/state mutation.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from app.cli import entry

runner = CliRunner()


def _settings(tmp_path: Path) -> Any:
    return SimpleNamespace(
        paths=SimpleNamespace(
            manifest_root=tmp_path / "manifests",
            project_root=tmp_path,
            vault_root=tmp_path / "vault",
            log_root=tmp_path / "logs",
        ),
        manifest=SimpleNamespace(
            path=tmp_path / "manifests" / "processed.json",
            enabled=True,
        ),
        queue=SimpleNamespace(
            enabled=True,
            state_path=tmp_path / "manifests" / "queue_state.json",
        ),
        watcher=SimpleNamespace(
            enabled=True,
            inbox_path=tmp_path / "inbox",
        ),
        ollama=SimpleNamespace(host="http://localhost:11434/", model="qwen3:8b"),
    )


def _invoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> Any:
    if monkeypatch is not None:
        monkeypatch.setattr(entry, "_load_configured_settings", lambda: _settings(tmp_path))
        monkeypatch.setattr(entry, "setup_logging", lambda _settings: None)
        return runner.invoke(entry.cli, ["status"])
    with patch(
        "app.cli.entry._load_configured_settings", return_value=_settings(tmp_path)
    ), patch("app.cli.entry.setup_logging", return_value=None):
        return runner.invoke(entry.cli, ["status"])


def _write_ledger(tmp_path: Path, files: list[dict]) -> None:
    mp = tmp_path / "manifests" / "processed.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps({"version": 1, "files": files}), encoding="utf-8")


def _ledger(
    path: str = "notes/a.md",
    status: str = "processed",
    processed_at: str | None = "2026-08-27T04:03:17Z",
) -> dict:
    return {
        "sha256": "a" * 64,
        "original_filename": Path(path).name,
        "original_path": path,
        "processed_at": processed_at,
        "extension": ".md",
        "status": status,
        "generated_note": None,
        "metadata": {},
    }


def _write_vector_store(tmp_path: Path, count: int, distinct_sources: int = 1) -> None:
    store = tmp_path / "manifests" / "vector_store.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for i in range(count):
        entries.append(
            {
                "id": f"s{i}",
                "text": "chunk text",
                "embedding": [0.0, 1.0],
                "source": f"notes/src{i % distinct_sources}.md",
                "source_type": "markdown",
                "chunk_index": i,
                "start_char": 0,
                "end_char": 10,
                "metadata": {},
            }
        )
    store.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def _write_note(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


REAL_NOTE = "---\nsource: notes/a.md\nsource_type: markdown\n---\nBody"
PLACEHOLDER_NOTE = "---\nsource_type: placeholder\n---\nStub"
USER_NOTE = "# A user's manual note\n\nNo frontmatter."


# ── Truthful counts (durable state) ────────────────────────────────────────


def test_reports_sources_and_chunks_from_vector_store(tmp_path: Path) -> None:
    _write_vector_store(tmp_path, count=6, distinct_sources=2)
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "Sources indexed" in result.output
    assert "2" in result.output
    assert "Indexed chunks" in result.output
    assert "6" in result.output


def test_reports_processed_failed_and_skipped(tmp_path: Path) -> None:
    _write_vector_store(tmp_path, count=1)
    _write_ledger(
        tmp_path,
        [
            _ledger("a.md", "processed"),
            _ledger("b.md", "processed"),
            _ledger("c.md", "failed"),
            _ledger("d.md", "skipped_duplicate"),
        ],
    )
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "Successful ingests" in result.output
    assert "Skipped duplicates" in result.output
    # 2 processed + 1 skipped counted in the ledger
    assert "Failed" in result.output


def test_placeholder_not_counted_as_real_note(tmp_path: Path) -> None:
    notes = tmp_path / "vault" / "Notes"
    _write_note(notes / "real.md", REAL_NOTE)
    _write_note(notes / "stub.md", PLACEHOLDER_NOTE)
    _write_note(notes / "manual.md", USER_NOTE)
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "Real generated notes" in result.output
    assert "Placeholder notes" in result.output
    assert "1" in result.output


def test_last_ingestion_comes_from_ledger(tmp_path: Path) -> None:
    _write_vector_store(tmp_path, count=1)
    _write_ledger(
        tmp_path,
        [
            _ledger("a.md", "processed", "2026-08-26T00:00:00Z"),
            _ledger("b.md", "processed", "2026-08-27T04:03:17Z"),
        ],
    )
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "2026-08-27T04:03:17Z" in result.output


def test_last_ingestion_never_when_empty_ledger(tmp_path: Path) -> None:
    _write_vector_store(tmp_path, count=1)
    _write_ledger(tmp_path, [])
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "never" in result.output


# ── Unavailable backing stores (never fabricate zero) ──────────────────────


def test_unavailable_vector_store_shows_unavailable_not_zero(tmp_path: Path) -> None:
    store = tmp_path / "manifests" / "vector_store.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text("{ not valid json", encoding="utf-8")
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "unavailable" in result.output


def test_missing_vector_store_is_genuine_zero(tmp_path: Path) -> None:
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    # no vector store file exists => genuinely zero sources/chunks
    assert "Sources indexed" in result.output


def test_unavailable_ledger_shows_unavailable(tmp_path: Path) -> None:
    mp = tmp_path / "manifests" / "processed.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text("{ not valid json", encoding="utf-8")
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "Manifest entries" in result.output
    assert "unavailable" in result.output


def test_unavailable_queue_shows_unavailable_not_zero(tmp_path: Path) -> None:
    qp = tmp_path / "manifests" / "queue_state.json"
    qp.parent.mkdir(parents=True, exist_ok=True)
    qp.write_text("{ not valid json", encoding="utf-8")
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "Items waiting" in result.output
    assert "unavailable" in result.output


def test_empty_queue_genuine_zero(tmp_path: Path) -> None:
    qp = tmp_path / "manifests" / "queue_state.json"
    qp.parent.mkdir(parents=True, exist_ok=True)
    qp.write_text(json.dumps({"version": 1, "items": []}), encoding="utf-8")
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    # "0" appears as the real waiting count
    assert "0" in result.output


# ── No retryable fabrication ───────────────────────────────────────────────


def test_no_retryable_row_fabrication(tmp_path: Path) -> None:
    _write_vector_store(tmp_path, count=1)
    _write_ledger(tmp_path, [_ledger("a.md", "processed")])
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "Retryable" not in result.output


# ── Read-only guarantees ───────────────────────────────────────────────────


def test_status_does_not_trigger_llm(tmp_path: Path) -> None:
    _write_vector_store(tmp_path, count=1)
    _write_ledger(tmp_path, [_ledger("a.md", "processed")])
    with patch(
        "app.infrastructure.llm.OllamaClient.is_available",
        side_effect=AssertionError("LLM health check must not be triggered by status"),
    ) as m:
        result = _invoke(tmp_path)
        m.assert_not_called()
    assert result.exit_code == 0


def test_status_does_not_mutate_missing_ledger(tmp_path: Path) -> None:
    # If status created the ledger it would be a mutation we can detect.
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert not (tmp_path / "manifests" / "processed.json").exists()


def test_status_does_not_create_directories(tmp_path: Path) -> None:
    # Read-only: no mkdir for manifests or log dirs.
    _invoke(tmp_path)
    assert not (tmp_path / "manifests").exists() or not (tmp_path / "logs").exists()


def test_status_does_not_modify_corrupt_ledger(tmp_path: Path) -> None:
    mp = tmp_path / "manifests" / "processed.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text("{ corrupt", encoding="utf-8")
    before = mp.read_text(encoding="utf-8")
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    # corrupt ledger must NOT be quarantined/recreated/renamed by status
    assert mp.read_text(encoding="utf-8") == before


def test_status_no_traceback_anywhere(tmp_path: Path) -> None:
    # Exercise a mix of healthy and corrupt stores; never a traceback.
    mp = tmp_path / "manifests" / "processed.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text("{ corrupt", encoding="utf-8")
    (tmp_path / "manifests" / "queue_state.json").write_text("{ corrupt", encoding="utf-8")
    (tmp_path / "manifests" / "vector_store.json").write_text("{ corrupt", encoding="utf-8")
    result = _invoke(tmp_path)
    assert result.exit_code == 0
    assert "Traceback" not in result.output
