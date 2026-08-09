"""Tests for the notebook ingestor upgrade (P2-605)."""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.document_intelligence import NotebookStructure
from app.infrastructure.ingestion.notebook_ingestor import NotebookIngestor


def _write_notebook(path: Path) -> None:
    nb = {
        "cells": [
            {"id": "md-1", "cell_type": "markdown", "source": ["# Analysis\n"], "outputs": []},
            {
                "id": "c-1",
                "cell_type": "code",
                "source": ["import pandas as pd\n"],
                "execution_count": 2,
                "outputs": [{"output_type": "stream", "text": ["<result>\n"]}],
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python"},
            "language_info": {"name": "python"},
        },
    }
    path.write_text(json.dumps(nb), encoding="utf-8")


class TestNotebookIngestor:
    def test_ingest_calls_parser(self, tmp_path: Path) -> None:
        path = tmp_path / "analysis.ipynb"
        _write_notebook(path)
        doc = NotebookIngestor().ingest(path)
        structure = doc.metadata.extra["notebook_structure"]
        assert isinstance(structure, NotebookStructure)
        assert len(structure.cells) == 2
        assert [c.type for c in structure.cells] == ["markdown", "code"]

    def test_ingest_preserves_flat_text(self, tmp_path: Path) -> None:
        path = tmp_path / "analysis.ipynb"
        _write_notebook(path)
        doc = NotebookIngestor().ingest(path)
        assert "```python" in doc.text
        assert "import pandas as pd" in doc.text

    def test_ingest_populates_metadata(self, tmp_path: Path) -> None:
        path = tmp_path / "analysis.ipynb"
        _write_notebook(path)
        doc = NotebookIngestor().ingest(path)
        assert doc.metadata.extra["cell_count"] == 2
        assert doc.metadata.extra["kernel"] == "Python 3"
        assert doc.metadata.extra["language"] == "python"

    def test_ingest_wires_max_cell_outputs_config(self, tmp_path: Path) -> None:
        path = tmp_path / "analysis.ipynb"
        nb = {
            "cells": [
                {
                    "id": "c-1",
                    "cell_type": "code",
                    "source": ["x = 1\n"],
                    "execution_count": 1,
                    "outputs": [
                        {"output_type": "stream", "text": [f"out{i}\n"]} for i in range(5)
                    ],
                }
            ],
            "metadata": {},
        }
        path.write_text(json.dumps(nb), encoding="utf-8")
        doc = NotebookIngestor(max_cell_outputs=2).ingest(path)
        structure = doc.metadata.extra["notebook_structure"]
        assert structure.cells[0].outputs == ["out0\n", "out1\n", "[truncated]"]
