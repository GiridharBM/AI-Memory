"""Tests for Code & Notebook domain models (P2-601)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.document_intelligence import (
    CodeClass,
    CodeFunction,
    CodeImport,
    CodeStructure,
    NotebookCell,
    NotebookStructure,
)

# ── CodeImport ───────────────────────────────────────────────────────────


class TestCodeImport:
    def test_round_trip(self) -> None:
        imp = CodeImport(module="os", names=["path", "getcwd"], level=0)
        data = imp.model_dump()
        restored = CodeImport.model_validate(data)
        assert restored == imp

    def test_defaults(self) -> None:
        imp = CodeImport(module="json")
        assert imp.names == []
        assert imp.level == 0

    def test_relative_import(self) -> None:
        imp = CodeImport(module="utils", names=["helper"], level=2)
        assert imp.level == 2

    def test_empty_module_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodeImport(module="")

    def test_negative_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodeImport(module="os", level=-1)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CodeImport(module="os", alias="x")  # type: ignore[call-arg]


# ── CodeFunction ─────────────────────────────────────────────────────────


class TestCodeFunction:
    def test_round_trip(self) -> None:
        fn = CodeFunction(
            name="hello",
            args=["name", "greeting"],
            docstring="Say hello.",
            start_line=10,
            end_line=15,
            start_char=200,
            end_char=350,
        )
        data = fn.model_dump()
        restored = CodeFunction.model_validate(data)
        assert restored == fn

    def test_defaults(self) -> None:
        fn = CodeFunction(name="f", start_line=1, end_line=2, start_char=0, end_char=5)
        assert fn.args == []
        assert fn.docstring is None

    def test_offset_validation_end_line_lt_start(self) -> None:
        with pytest.raises(ValidationError, match="end_line"):
            CodeFunction(name="f", start_line=10, end_line=5, start_char=0, end_char=10)

    def test_offset_validation_end_char_lt_start(self) -> None:
        with pytest.raises(ValidationError, match="end_char"):
            CodeFunction(name="f", start_line=1, end_line=2, start_char=10, end_char=5)

    def test_equal_offsets_allowed(self) -> None:
        fn = CodeFunction(name="f", start_line=1, end_line=1, start_char=0, end_char=0)
        assert fn.start_line == fn.end_line

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodeFunction(name="", start_line=1, end_line=2, start_char=0, end_char=5)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CodeFunction(name="f", start_line=1, end_line=2, start_char=0, end_char=5, x=1)  # type: ignore[call-arg]


# ── CodeClass ────────────────────────────────────────────────────────────


class TestCodeClass:
    def test_round_trip(self) -> None:
        method = CodeFunction(
            name="__init__",
            args=["self"],
            start_line=11,
            end_line=13,
            start_char=210,
            end_char=260,
        )
        cls = CodeClass(
            name="MyClass",
            bases=["BaseClass"],
            methods=[method],
            docstring="A test class.",
            start_line=10,
            end_line=20,
            start_char=200,
            end_char=500,
        )
        data = cls.model_dump()
        restored = CodeClass.model_validate(data)
        assert restored == cls
        assert len(restored.methods) == 1
        assert restored.methods[0].name == "__init__"

    def test_defaults(self) -> None:
        cls = CodeClass(name="C", start_line=1, end_line=5, start_char=0, end_char=50)
        assert cls.bases == []
        assert cls.methods == []
        assert cls.docstring is None

    def test_offset_validation(self) -> None:
        with pytest.raises(ValidationError, match="end_line"):
            CodeClass(name="C", start_line=5, end_line=1, start_char=0, end_char=50)

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodeClass(name="", start_line=1, end_line=5, start_char=0, end_char=50)


# ── CodeStructure ────────────────────────────────────────────────────────


class TestCodeStructure:
    def test_round_trip(self) -> None:
        cs = CodeStructure(
            language="python",
            imports=[CodeImport(module="os")],
            functions=[
                CodeFunction(name="main", start_line=10, end_line=12, start_char=100, end_char=150)
            ],
            classes=[
                CodeClass(name="Foo", start_line=20, end_line=30, start_char=200, end_char=500)
            ],
            docstrings=["Module docstring."],
            char_start=0,
            char_end=1000,
        )
        data = cs.model_dump()
        restored = CodeStructure.model_validate(data)
        assert restored == cs

    def test_defaults(self) -> None:
        cs = CodeStructure()
        assert cs.language == "generic"
        assert cs.imports == []
        assert cs.functions == []
        assert cs.classes == []
        assert cs.docstrings == []
        assert cs.char_start == 0
        assert cs.char_end == 0

    def test_empty_structure_valid(self) -> None:
        cs = CodeStructure(language="javascript")
        assert cs.language == "javascript"
        assert len(cs.imports) == 0

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CodeStructure(x=1)  # type: ignore[call-arg]


# ── NotebookCell ─────────────────────────────────────────────────────────


class TestNotebookCell:
    def test_round_trip(self) -> None:
        cell = NotebookCell(
            id="cell-1",
            type="code",
            source="print('hello')",
            outputs=["hello"],
            execution_count=1,
        )
        data = cell.model_dump()
        restored = NotebookCell.model_validate(data)
        assert restored == cell

    def test_markdown_cell(self) -> None:
        cell = NotebookCell(id="cell-0", type="markdown", source="# Title")
        assert cell.outputs == []
        assert cell.execution_count is None

    def test_raw_cell(self) -> None:
        cell = NotebookCell(id="cell-2", type="raw", source="raw content")
        assert cell.type == "raw"

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NotebookCell(id="x", type="unknown", source="")  # type: ignore[call-arg]

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NotebookCell(id="", type="code")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            NotebookCell(id="x", type="code", foo="bar")  # type: ignore[call-arg]


# ── NotebookStructure ────────────────────────────────────────────────────


class TestNotebookStructure:
    def test_round_trip(self) -> None:
        ns = NotebookStructure(
            cells=[
                NotebookCell(id="0", type="markdown", source="# Hello"),
                NotebookCell(id="1", type="code", source="x = 1", execution_count=1),
            ],
            kernel="Python 3",
            language="python",
        )
        data = ns.model_dump()
        restored = NotebookStructure.model_validate(data)
        assert restored == ns
        assert len(restored.cells) == 2
        assert restored.cells[1].execution_count == 1

    def test_defaults(self) -> None:
        ns = NotebookStructure()
        assert ns.cells == []
        assert ns.kernel == ""
        assert ns.language == ""

    def test_empty_notebook_valid(self) -> None:
        ns = NotebookStructure(language="r")
        assert len(ns.cells) == 0

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            NotebookStructure(metadata="x")  # type: ignore[call-arg]


# ── Cross-model composition ──────────────────────────────────────────────


class TestComposition:
    def test_code_structure_with_nested_class_methods(self) -> None:
        cs = CodeStructure(
            language="python",
            classes=[
                CodeClass(
                    name="Service",
                    bases=["BaseService"],
                    methods=[
                        CodeFunction(
                            name="__init__", args=["self", "config"],
                            start_line=10, end_line=12,
                            start_char=100, end_char=150,
                        ),
                        CodeFunction(
                            name="run", args=["self"],
                            docstring="Run the service.",
                            start_line=14, end_line=20,
                            start_char=160, end_char=300,
                        ),
                    ],
                    start_line=9,
                    end_line=21,
                    start_char=90,
                    end_char=310,
                ),
            ],
        )
        assert len(cs.classes) == 1
        assert len(cs.classes[0].methods) == 2
        assert cs.classes[0].methods[1].docstring == "Run the service."

    def test_notebook_structure_with_multiple_cell_types(self) -> None:
        ns = NotebookStructure(
            cells=[
                NotebookCell(
                    id="md-1", type="markdown", source="## Analysis",
                ),
                NotebookCell(
                    id="code-1", type="code",
                    source="import pandas as pd", execution_count=1,
                ),
                NotebookCell(
                    id="code-2", type="code", source="df.head()",
                    outputs=["<table>"], execution_count=2,
                ),
                NotebookCell(id="raw-1", type="raw", source="raw data"),
            ],
            kernel="Python 3 (ipykernel)",
            language="python",
        )
        types = [c.type for c in ns.cells]
        assert types == ["markdown", "code", "code", "raw"]
        assert ns.cells[2].outputs == ["<table>"]
