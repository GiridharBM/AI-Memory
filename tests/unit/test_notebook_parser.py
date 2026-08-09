"""Tests for the Jupyter notebook parser (P2-605)."""

from __future__ import annotations

import logging

from app.domain.document_intelligence import NotebookStructure
from app.infrastructure.document_intelligence.code import notebook as notebook_module
from app.infrastructure.document_intelligence.code import parse_notebook
from app.infrastructure.document_intelligence.code.notebook import NotebookParser


def _code_cell(cell_id: str, source: list[str], execution_count: int | None = None) -> dict:
    return {
        "id": cell_id,
        "cell_type": "code",
        "source": source,
        "execution_count": execution_count,
        "outputs": [],
    }


class TestNotebookParser:
    def test_parse_valid_notebook(self) -> None:
        nb = {
            "cells": [
                {"id": "md-1", "cell_type": "markdown", "source": ["# Title\n"], "outputs": []},
                _code_cell("c-1", ["x = 1\n"]),
                _code_cell("c-2", ["x + 1\n"]),
            ],
            "metadata": {},
        }
        cs = parse_notebook(nb)
        assert len(cs.cells) == 3
        assert [c.type for c in cs.cells] == ["markdown", "code", "code"]
        assert [c.id for c in cs.cells] == ["md-1", "c-1", "c-2"]
        assert cs.cells[0].source == "# Title\n"

    def test_parse_preserves_execution_count(self) -> None:
        nb = {"cells": [_code_cell("c-1", ["x = 1\n"], execution_count=5)], "metadata": {}}
        cs = parse_notebook(nb)
        assert cs.cells[0].execution_count == 5

    def test_parse_extracts_outputs(self) -> None:
        nb = {
            "cells": [
                {
                    "id": "c-1",
                    "cell_type": "code",
                    "source": ["print('hi')\n"],
                    "execution_count": 1,
                    "outputs": [{"output_type": "stream", "text": ["hi\n"]}],
                }
            ],
            "metadata": {},
        }
        cs = parse_notebook(nb)
        assert cs.cells[0].outputs == ["hi\n"]

    def test_parse_caps_outputs(self, monkeypatch) -> None:
        monkeypatch.setattr(notebook_module, "_MAX_CELL_OUTPUTS", 10)
        outputs = [{"output_type": "stream", "text": [f"out{i}\n"]} for i in range(20)]
        nb = {"cells": [_code_cell("c-1", ["x = 1\n"], 1)], "metadata": {}}
        nb["cells"][0]["outputs"] = outputs
        cs = parse_notebook(nb)
        assert len(cs.cells[0].outputs) == 11
        assert cs.cells[0].outputs[:10] == [f"out{i}\n" for i in range(10)]
        assert cs.cells[0].outputs[-1] == "[truncated]"

    def test_max_cell_outputs_parameter_overrides_default(self) -> None:
        outputs = [{"output_type": "stream", "text": [f"out{i}\n"]} for i in range(5)]
        nb = {"cells": [_code_cell("c-1", ["x = 1\n"], 1)], "metadata": {}}
        nb["cells"][0]["outputs"] = outputs
        cs = parse_notebook(nb, max_cell_outputs=2)
        assert cs.cells[0].outputs == ["out0\n", "out1\n", "[truncated]"]

    def test_parse_empty_notebook(self) -> None:
        cs = parse_notebook({"cells": [], "metadata": {}})
        assert isinstance(cs, NotebookStructure)
        assert cs.cells == []
        assert cs.kernel == ""
        assert cs.language == ""

    def test_parse_malformed_cell(self, caplog) -> None:
        nb = {
            "cells": [
                {"id": "bad-1", "source": ["oops\n"]},
                _code_cell("good-1", ["x = 1\n"]),
            ],
            "metadata": {},
        }
        with caplog.at_level(logging.WARNING):
            cs = parse_notebook(nb)
        assert len(cs.cells) == 1
        assert cs.cells[0].id == "good-1"
        assert "cell_type" in caplog.text

    def test_parse_extracts_kernel(self) -> None:
        nb = {
            "cells": [],
            "metadata": {"kernelspec": {"display_name": "Python 3 (ipykernel)"}},
        }
        cs = parse_notebook(nb)
        assert cs.kernel == "Python 3 (ipykernel)"

    def test_parse_extracts_language(self) -> None:
        nb = {"cells": [], "metadata": {"language_info": {"name": "python"}}}
        cs = parse_notebook(nb)
        assert cs.language == "python"

    def test_never_raises(self) -> None:
        cs = parse_notebook({"foo": "bar", "nested": {"a": 1}})
        assert isinstance(cs, NotebookStructure)
        assert cs.cells == []
        cs2 = parse_notebook({"cells": ["not-a-dict", 42, None]})
        assert cs2.cells == []
        cs3 = NotebookParser().parse("garbage")  # type: ignore[arg-type]
        assert cs3.cells == []

    def test_cell_id_falls_back_to_index(self) -> None:
        nb = {"cells": [{"cell_type": "markdown", "source": ["# T\n"]}], "metadata": {}}
        cs = parse_notebook(nb)
        assert cs.cells[0].id == "0"

    def test_non_int_execution_count_ignored(self) -> None:
        nb = {"cells": [_code_cell("c-1", ["x=1\n"], execution_count="3")], "metadata": {}}
        cs = parse_notebook(nb)
        assert cs.cells[0].execution_count is None

    def test_source_as_single_string(self) -> None:
        nb = {
            "cells": [{"id": "c-1", "cell_type": "code", "source": "x = 1", "outputs": []}],
            "metadata": {},
        }
        cs = parse_notebook(nb)
        assert cs.cells[0].source == "x = 1"

    def test_output_forms(self) -> None:
        nb = {
            "cells": [
                {
                    "id": "c-1",
                    "cell_type": "code",
                    "source": ["x=1\n"],
                    "outputs": [
                        "plain-string-output",
                        {"output_type": "error", "text": "boom"},
                        {"output_type": "display_data", "data": {"text/plain": ["<fig>\n"]}},
                    ],
                }
            ],
            "metadata": {},
        }
        cs = parse_notebook(nb)
        outputs = cs.cells[0].outputs
        assert outputs[0] == "plain-string-output"
        assert outputs[1] == "boom"
        assert "<fig>" in outputs[2]
