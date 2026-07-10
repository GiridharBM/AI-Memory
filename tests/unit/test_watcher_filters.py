"""Tests for watcher file filtering."""

from __future__ import annotations

from pathlib import Path

from app.watcher.scanner import should_watch_file


def test_markdown_detected(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Notes", encoding="utf-8")

    assert should_watch_file(path)


def test_txt_ignored(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("Notes", encoding="utf-8")

    assert not should_watch_file(path)


def test_pdf_ignored(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF")

    assert not should_watch_file(path)


def test_hidden_ignored(tmp_path: Path) -> None:
    path = tmp_path / ".hidden.md"
    path.write_text("# Hidden", encoding="utf-8")

    assert not should_watch_file(path)


def test_temporary_ignored(tmp_path: Path) -> None:
    tilde_path = tmp_path / "notes.md~"
    tmp_path_file = tmp_path / "notes.md.tmp"
    tilde_path.write_text("# Temp", encoding="utf-8")
    tmp_path_file.write_text("# Temp", encoding="utf-8")

    assert not should_watch_file(tilde_path)
    assert not should_watch_file(tmp_path_file)
