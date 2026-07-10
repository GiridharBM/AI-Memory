"""Tests for file hashing helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.infrastructure.state.hashing import compute_file_hash


def test_compute_file_hash_for_markdown(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    content = ("hello world\n" * 1000).encode("utf-8")
    path.write_bytes(content)

    assert compute_file_hash(path) == hashlib.sha256(content).hexdigest()


def test_compute_file_hash_for_txt(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    content = b"text content"
    path.write_bytes(content)

    assert compute_file_hash(path) == hashlib.sha256(content).hexdigest()


def test_compute_file_hash_for_pdf(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    content = b"%PDF-1.4"
    path.write_bytes(content)

    assert compute_file_hash(path) == hashlib.sha256(content).hexdigest()


def test_compute_file_hash_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("a,b", encoding="utf-8")

    with pytest.raises(ValueError):
        compute_file_hash(path)
