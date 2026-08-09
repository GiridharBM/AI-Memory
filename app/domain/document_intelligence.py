"""Shared domain models for the document intelligence layer (frozen §7.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MetadataExtraction(BaseModel):
    """Metadata values extracted from a source document (P2-201)."""

    model_config = ConfigDict(extra="forbid")

    source_type: str
    values: dict[str, Any] = Field(default_factory=dict)
    extractor: str


BlockType = Literal["paragraph", "list", "code", "blockquote", "table"]


class DocumentBlock(BaseModel):
    """A typed block within a document section (frozen spec §4.2)."""

    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1)
    type: BlockType
    text: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_offsets(self) -> DocumentBlock:
        if self.end_char < self.start_char:
            raise ValueError("end_char must be >= start_char")
        if len(self.text) != self.end_char - self.start_char:
            raise ValueError(
                "len(text) must equal end_char - start_char "
                "(start_char inclusive, end_char exclusive)"
            )
        return self


class DocumentSection(BaseModel):
    """A heading-delimited section of the document (frozen spec §4.2)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str
    level: int = Field(ge=1, le=6)
    parent_id: str | None = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    blocks: list[DocumentBlock]

    @model_validator(mode="after")
    def _validate_offsets(self) -> DocumentSection:
        if self.end_char < self.start_char:
            raise ValueError("end_char must be >= start_char")
        return self


class DocumentStructure(BaseModel):
    """The nested structure of a document (frozen spec §4.2)."""

    model_config = ConfigDict(extra="forbid")

    sections: list[DocumentSection]


class TableCell(BaseModel):
    """A single normalized table cell value (frozen spec §4.4)."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(default="")


class TableHeader(BaseModel):
    """The header row of a table (frozen spec §4.4)."""

    model_config = ConfigDict(extra="forbid")

    cells: list[TableCell] = Field(default_factory=list)


class TableRow(BaseModel):
    """A data row of a table (frozen spec §4.4)."""

    model_config = ConfigDict(extra="forbid")

    cells: list[TableCell] = Field(default_factory=list)


class Table(BaseModel):
    """A typed table extracted from a source document (frozen spec §4.4)."""

    model_config = ConfigDict(extra="forbid")

    title: str
    header: TableHeader = Field(default_factory=TableHeader)
    rows: list[TableRow] = Field(default_factory=list)
    source_position: str = ""  # provenance: sheet/page/line per extractor (O3)


class ImageExif(BaseModel):
    """Raw EXIF fields read from an image file (frozen spec §4.5, P2-502).

    Values are kept in EXIF tag order, decoded when possible; the raw tag
    number is preserved so unknown tags survive round-trips.
    """

    model_config = ConfigDict(extra="forbid")

    raw: dict[int, str] = Field(default_factory=dict)
    decoded: dict[str, str] = Field(default_factory=dict)


class ImageInfo(BaseModel):
    """Metadata describing a single image (frozen spec §4.5, P2-501).

    Produced at ingestion for standalone image files and at enrichment time
    for images embedded in PDFs (``page_no`` then carries provenance).
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    format: str  # e.g. "JPEG", "PNG" (Pillow format string or extension)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    mode: str = ""  # e.g. "RGB", "RGBA", "L"
    page_no: int | None = Field(default=None, ge=1)  # provenance for PDF-embedded images (P2-506)
    index: int = Field(default=0, ge=0)  # position within the page/document
    exif: ImageExif = Field(default_factory=ImageExif)


# ── Code & Notebook Intelligence (frozen spec §4.6, P2-601) ─────────────


class CodeImport(BaseModel):
    """An import statement extracted from a code file (frozen spec §4.6, P2-601)."""

    model_config = ConfigDict(extra="forbid")

    module: str = Field(min_length=1)
    names: list[str] = Field(default_factory=list)
    level: int = Field(default=0, ge=0)  # relative import depth (0 = absolute)


class CodeFunction(BaseModel):
    """A function definition extracted from a code file (frozen spec §4.6, P2-601)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    docstring: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_offsets(self) -> CodeFunction:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.end_char < self.start_char:
            raise ValueError("end_char must be >= start_char")
        return self


class CodeClass(BaseModel):
    """A class definition extracted from a code file (frozen spec §4.6, P2-601)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    bases: list[str] = Field(default_factory=list)
    methods: list[CodeFunction] = Field(default_factory=list)
    docstring: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_offsets(self) -> CodeClass:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.end_char < self.start_char:
            raise ValueError("end_char must be >= start_char")
        return self


class CodeStructure(BaseModel):
    """Parsed structure of a code file (frozen spec §4.6, P2-601).

    Produced by the AST parser (Python) or heuristic fallback (other languages).
    """

    model_config = ConfigDict(extra="forbid")

    language: str = "generic"
    imports: list[CodeImport] = Field(default_factory=list)
    functions: list[CodeFunction] = Field(default_factory=list)
    classes: list[CodeClass] = Field(default_factory=list)
    docstrings: list[str] = Field(default_factory=list)
    char_start: int = Field(default=0, ge=0)
    char_end: int = Field(default=0, ge=0)


class NotebookCell(BaseModel):
    """A single cell in a Jupyter notebook (frozen spec §4.6, P2-601)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: Literal["markdown", "code", "raw"]
    source: str = ""
    outputs: list[str] = Field(default_factory=list)
    execution_count: int | None = None


class NotebookStructure(BaseModel):
    """Parsed structure of a Jupyter notebook (frozen spec §4.6, P2-601).

    Produced by NotebookParser.parse() from the full notebook dict.
    """

    model_config = ConfigDict(extra="forbid")

    cells: list[NotebookCell] = Field(default_factory=list)
    kernel: str = ""
    language: str = ""
