"""Unit tests for table extraction, rendering, and note-body integration (M2.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.document_intelligence import (
    Table,
    TableCell,
    TableHeader,
    TableRow,
)
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.tables import (
    extract_tables,
    get_default_table_extractor,
)
from app.infrastructure.document_intelligence.tables.extractor import (
    CsvTableExtractor,
    PdfTableExtractor,
    SpreadsheetTableExtractor,
    TableExtractorRegistry,
)
from app.infrastructure.document_intelligence.tables.render import (
    MarkdownTableRenderer,
    render_tables_to_markdown,
)
from app.templates.obsidian_note import ObsidianMarkdownGenerator

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tables"


def _document(
    text: str, *, source_type: str = "csv", filename: str | None = None
) -> SourceDocument:
    return SourceDocument(
        source="tables.csv",
        source_type=source_type,
        filename=filename or "tables.csv",
        text=text,
        metadata=DocumentMetadata(),
    )


class TestModels:
    def test_table_round_trips(self) -> None:
        table = Table(
            title="t",
            header=TableHeader(cells=[TableCell(value="a")]),
            rows=[TableRow(cells=[TableCell(value="b")])],
            source_position="line 1",
        )
        restored = Table.model_validate(table.model_dump(mode="json"))
        assert restored == table

    def test_table_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Table.model_validate(
                {"title": "t", "header": {}, "rows": [], "confidence": 0.9}
            )

    def test_empty_table_is_valid(self) -> None:
        table = Table.model_validate({"title": "t"})
        assert table.header.cells == []
        assert table.rows == []


class TestCsvExtraction:
    def test_simple_csv_extracts_single_table(self) -> None:
        doc = _document("name,age\nAlice,30\nBob,25\n")
        tables = extract_tables(doc)
        assert len(tables) == 1
        table = tables[0]
        assert table.title == "tables.csv"
        assert [c.value for c in table.header.cells] == ["name", "age"]
        assert [[c.value for c in row.cells] for row in table.rows] == [
            ["Alice", "30"],
            ["Bob", "25"],
        ]
        assert table.source_position == "line 1"

    def test_tsv_detected_via_sniffer(self) -> None:
        doc = _document("name\tage\nAlice\t30\nBob\t25\n")
        tables = extract_tables(doc)
        assert len(tables) == 1
        assert [[c.value for c in row.cells] for row in tables[0].rows] == [
            ["Alice", "30"],
            ["Bob", "25"],
        ]

    def test_header_sniffing_disabled_treats_first_row_as_data(self) -> None:
        extractor = CsvTableExtractor(header_sniffing=False)
        doc = _document("name,age\nAlice,30\n")
        tables = extractor.extract(doc)
        assert [c.value for c in tables[0].header.cells] == []
        assert [[c.value for c in row.cells] for row in tables[0].rows] == [
            ["name", "age"],
            ["Alice", "30"],
        ]

    def test_empty_text_yields_no_tables(self) -> None:
        assert extract_tables(_document("")) == []

    def test_quoted_escaped_fields_parse(self) -> None:
        doc = _document('name,note\nAlice,"hello, world"\nBob,"line1\nline2"\n')
        tables = extract_tables(doc)
        assert [c.value for c in tables[0].header.cells] == ["name", "note"]
        assert [[c.value for c in row.cells] for row in tables[0].rows] == [
            ["Alice", "hello, world"],
            ["Bob", "line1\nline2"],
        ]

    def test_uniform_delimiter_falls_back_to_excel_dialect(self) -> None:
        doc = _document("aaaa\nbbbb\ncccc\n")
        tables = extract_tables(doc)
        assert len(tables) == 1
        assert [c.value for c in tables[0].header.cells] == ["aaaa"]

    def test_row_cap_truncates(self) -> None:
        extractor = CsvTableExtractor(max_rows=2)
        doc = _document("name,age\nAlice,30\nBob,25\nCarol,40\n")
        tables = extractor.extract(doc)
        assert [[c.value for c in row.cells] for row in tables[0].rows] == [
            ["Alice", "30"],
            ["Bob", "25"],
        ]

    def test_blank_data_rows_dropped(self) -> None:
        doc = _document("name,age\nAlice,30\n\nBob,25\n\n")
        tables = extract_tables(doc)
        assert [[c.value for c in row.cells] for row in tables[0].rows] == [
            ["Alice", "30"],
            ["Bob", "25"],
        ]

    def test_only_blank_rows_yields_no_table(self) -> None:
        extractor = CsvTableExtractor()
        doc = _document(",,,\n,,,\n")
        assert extractor.extract(doc) == []

    def test_extract_tables_unregistered_kind_yields_empty(self) -> None:
        doc = _document("# Heading\n\nBody.\n", source_type="markdown")
        assert extract_tables(doc) == []


class TestSpreadsheetExtraction:
    def test_multi_sheet_and_merged_cells(self) -> None:
        extractor = SpreadsheetTableExtractor()
        doc = SourceDocument(
            source="multi_sheet.xlsx",
            source_type="spreadsheet",
            filename="multi_sheet.xlsx",
            text="",
            metadata=DocumentMetadata(),
            source_path=FIXTURES / "multi_sheet.xlsx",
        )
        tables = extractor.extract(doc)
        assert [t.title for t in tables] == ["Sheet1", "Merged"]
        assert [[c.value for c in row.cells] for row in tables[1].rows] == [
            ["top-left", "top-left"],
            ["", "x"],
        ]

    def test_missing_source_path_returns_empty(self) -> None:
        extractor = SpreadsheetTableExtractor()
        doc = _document("", source_type="spreadsheet")
        assert extractor.extract(doc) == []

    def test_row_cap_truncates(self) -> None:
        extractor = SpreadsheetTableExtractor(max_rows=2)
        doc = SourceDocument(
            source="caps.xlsx",
            source_type="spreadsheet",
            filename="caps.xlsx",
            text="",
            metadata=DocumentMetadata(),
            source_path=FIXTURES / "multi_sheet.xlsx",
        )
        tables = extractor.extract(doc)
        assert [len(t.rows) for t in tables] == [2, 2]

    def test_corrupt_workbook_contained(self, tmp_path: Path) -> None:
        extractor = SpreadsheetTableExtractor()
        corrupt = tmp_path / "corrupt.xlsx"
        corrupt.write_bytes(b"not a zip file")
        doc = SourceDocument(
            source="corrupt.xlsx",
            source_type="spreadsheet",
            filename="corrupt.xlsx",
            text="",
            metadata=DocumentMetadata(),
            source_path=corrupt,
        )
        assert extractor.extract(doc) == []


class TestPdfExtraction:
    def test_absent_engine_degrades_to_flat_fallback(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Engine missing → empty list + warning (frozen C-3), strictly enforced.

        The import is forced to fail regardless of whether pdfplumber is
        installed, so this test is enforceable in every environment (review R2).
        """
        import builtins
        import types
        from collections.abc import Mapping, Sequence

        real_import = builtins.__import__

        def _block_pdfplumber(
            name: str,
            globals_: Mapping[str, object] | None = None,
            locals_: Mapping[str, object] | None = None,
            fromlist: Sequence[str] = (),
            level: int = 0,
        ) -> types.ModuleType:
            if name == "pdfplumber":
                raise ImportError("pdfplumber disabled for test")
            return real_import(name, globals_, locals_, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _block_pdfplumber)
        extractor = PdfTableExtractor()
        doc = SourceDocument(
            source="rules.pdf",
            source_type="pdf",
            filename="rules.pdf",
            text="",
            metadata=DocumentMetadata(),
            source_path=FIXTURES / "ruled_table.pdf",
        )
        with caplog.at_level("WARNING", logger="app.infrastructure.document_intelligence.tables"):
            tables = extractor.extract(doc)
        assert tables == []
        assert any("pdfplumber" in r.message for r in caplog.records)

    @pytest.mark.integration
    def test_engine_present_extracts_ruled_table(self) -> None:
        """Ruled-table PDF → Table → Markdown when pdfplumber is installed (P2-405 AC).

        Skipped when the optional engine is absent; the engine-present path is
        enforced by this test (review R2).
        """
        pytest.importorskip("pdfplumber")
        extractor = PdfTableExtractor()
        doc = SourceDocument(
            source="rules.pdf",
            source_type="pdf",
            filename="rules.pdf",
            text="",
            metadata=DocumentMetadata(),
            source_path=FIXTURES / "ruled_table.pdf",
        )
        tables = extractor.extract(doc)
        assert len(tables) >= 1
        assert all(isinstance(t, Table) for t in tables)
        markdown = MarkdownTableRenderer().to_markdown(tables[0])
        assert markdown.startswith("|") and "| --- |" in markdown


class TestRegistry:
    def test_select_by_kind(self) -> None:
        registry = get_default_table_extractor()
        assert registry.select("csv") is not None
        assert registry.select("spreadsheet") is not None
        assert registry.select("pdf") is not None

    def test_empty_registry_select_returns_none(self) -> None:
        registry = TableExtractorRegistry([])
        assert registry.select("csv") is None

    def test_unregistered_kind_returns_none(self) -> None:
        registry = get_default_table_extractor()
        assert registry.select("markdown") is None


class TestEnrichmentGate:
    def test_flag_or_pdf_kind_triggers_extraction(self) -> None:
        from unittest.mock import MagicMock

        from app.pipelines.ingest_workflow import IngestionWorkflow

        wf = IngestionWorkflow(
            ingestion_service=MagicMock(),
            ollama_client=MagicMock(),
            note_generator=MagicMock(),
            writer=MagicMock(),
        )
        doc = _document("name,age\nAlice,30\n", source_type="csv")

        with_flag = wf._enrich_tables(doc, "csv", requires_table_extraction=True)
        assert with_flag is not None
        assert with_flag[0]["title"] == "tables.csv"

        csv_without_flag = wf._enrich_tables(doc, "csv")
        assert csv_without_flag is None

        pdf = wf._enrich_tables(doc, "pdf")
        assert pdf is None  # csv text, no pdfplumber -> engine missing -> flat fallback


class TestRenderer:
    def test_render_basic_table(self) -> None:
        doc = _document("name,age\nAlice,30\n")
        table = extract_tables(doc)[0]
        markdown = MarkdownTableRenderer().to_markdown(table)
        assert markdown == "| name | age |\n| --- | --- |\n| Alice | 30 |"

    def test_render_escapes_pipes_and_newlines(self) -> None:
        table = Table(
            title="t",
            header=TableHeader(cells=[TableCell(value="col")]),
            rows=[TableRow(cells=[TableCell(value="a|b\nc")])],
        )
        markdown = MarkdownTableRenderer().to_markdown(table)
        assert "| a\\|b<br>c |" in markdown

    def test_render_tables_to_markdown_filters_empty(self) -> None:
        assert render_tables_to_markdown([]) == []
        doc = _document("name,age\nAlice,30\n")
        rendered = render_tables_to_markdown(extract_tables(doc))
        assert len(rendered) == 1


class TestGoldenFile:
    def test_csv_fixture_renders_to_committed_golden_markdown(self) -> None:
        text = (FIXTURES / "people.csv").read_text(encoding="utf-8")
        expected = (FIXTURES / "people.expected.md").read_text(encoding="utf-8").rstrip()
        doc = SourceDocument(
            source="people.csv",
            source_type="csv",
            filename="people.csv",
            text=text,
            metadata=DocumentMetadata(),
        )
        tables = extract_tables(doc)
        rendered = "\n\n".join(MarkdownTableRenderer().to_markdown(t) for t in tables)
        assert rendered == expected


class TestNoteBodyRendering:
    def test_tables_in_extra_render_into_note_body(self) -> None:
        doc = _document("name,age\nAlice,30\n")
        table = extract_tables(doc)[0]
        doc.metadata.extra["tables"] = [table.model_dump(mode="json")]
        note = ObsidianMarkdownGenerator().generate(document=doc, analysis=_analysis())
        assert "## Tables" in note.markdown
        assert "| name | age |" in note.markdown
        assert "| Alice | 30 |" in note.markdown

    def test_no_tables_key_preserves_phase1_output(self) -> None:
        doc = _document("name,age\nAlice,30\n")
        note = ObsidianMarkdownGenerator().generate(document=doc, analysis=_analysis())
        assert "## Tables" not in note.markdown
        assert "| name | age |" not in note.markdown

    def test_tables_disabled_means_flat_notes(self) -> None:
        doc = _document("name,age\nAlice,30\n")
        note = ObsidianMarkdownGenerator().generate(document=doc, analysis=_analysis())
        assert "## Tables" not in note.markdown


def _analysis() -> object:
    from app.domain.analysis import DocumentAnalysis

    return DocumentAnalysis.model_validate(
        {
            "suggested_note_title": "Local AI Memory",
            "summary": {"short": "s", "detailed": "d"},
            "key_concepts": [],
            "definitions": [],
            "important_entities": [],
            "related_topics": [],
            "tags": [],
        }
    )
