"""Tests for the metadata extraction protocol and registry (P2-201)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.document_intelligence import MetadataExtraction
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.metadata import (
    DocumentMetadataService,
    MetadataExtractor,
    get_default_metadata_service,
    register_extractor,
)


class _FakeExtractor:
    """Minimal MetadataExtractor implementation for registry tests."""

    name = "fake"

    def __init__(self, source_types: tuple[str, ...], values: dict | None = None) -> None:
        self.source_types = source_types
        self._values = values or {}

    def extract(self, document: SourceDocument) -> dict:
        return dict(self._values)


def _source_document(source_type: str = "pdf") -> SourceDocument:
    return SourceDocument(
        source="sample.pdf",
        source_path=None,
        source_type=source_type,
        filename="sample.pdf",
        text="",
        metadata=DocumentMetadata(),
    )


def test_extractor_is_runtime_checkable():
    assert isinstance(_FakeExtractor(("pdf",)), MetadataExtractor)


def test_register_and_select_by_source_type():
    pdf = _FakeExtractor(("pdf",))
    audio = _FakeExtractor(("audio",))
    service = DocumentMetadataService()
    service.register(pdf)
    service.register(audio)

    assert service.extractors_for("pdf") == [pdf]
    assert service.extractors_for("audio") == [audio]
    assert service.extractors_for("docx") == []


def test_extractors_for_returns_registration_order():
    first = _FakeExtractor(("pdf", "docx"))
    second = _FakeExtractor(("pdf",))
    service = DocumentMetadataService(extractors=[first, second])

    assert service.extractors_for("pdf") == [first, second]


def test_duplicate_registration_is_idempotent():
    pdf = _FakeExtractor(("pdf",))
    service = DocumentMetadataService()
    service.register(pdf)
    service.register(pdf)

    assert len(service.extractors) == 1


def test_register_duplicate_instances_both_kept():
    first = _FakeExtractor(("pdf",))
    second = _FakeExtractor(("pdf",))
    service = DocumentMetadataService()
    service.register(first)
    service.register(second)

    assert service.extractors_for("pdf") == [first, second]


def test_extract_merges_matching_extractors_in_order():
    service = DocumentMetadataService(
        extractors=[
            _FakeExtractor(("pdf",), {"title": "First", "author": "A"}),
            _FakeExtractor(("pdf",), {"title": "Second", "page_count": 3}),
        ]
    )

    extraction = service.extract(_source_document())

    assert extraction.source_type == "pdf"
    assert extraction.values == {"title": "Second", "author": "A", "page_count": 3}
    assert "fake" in extraction.extractor


def test_extract_with_no_matching_extractor_returns_empty():
    service = DocumentMetadataService(extractors=[_FakeExtractor(("audio",))])

    extraction = service.extract(_source_document(source_type="pdf"))

    assert extraction.source_type == "pdf"
    assert extraction.values == {}


def test_extract_never_raises_for_unknown_source_type():
    service = DocumentMetadataService()

    extraction = service.extract(_source_document(source_type="video"))

    assert extraction.values == {}


def test_merge_writes_known_fields_and_routes_unknown_to_extra():
    metadata = DocumentMetadata(title="original", extra={"existing": 1})
    extraction = MetadataExtraction(
        source_type="pdf",
        values={
            "title": "new title",
            "author": "someone",
            "created_at": datetime(2024, 1, 1, tzinfo=UTC),
            "custom_field": "custom value",
        },
        extractor="fake",
    )

    merged = DocumentMetadataService.merge(metadata, extraction)

    assert merged.title == "new title"
    assert merged.author == "someone"
    assert merged.created_at == datetime(2024, 1, 1, tzinfo=UTC)
    assert merged.extra == {"existing": 1, "custom_field": "custom value"}
    assert metadata.title == "original"


def test_merge_preserves_original_extra_keys():
    metadata = DocumentMetadata(extra={"keep": "me"})
    extraction = MetadataExtraction(source_type="pdf", values={"title": "x"}, extractor="fake")

    merged = DocumentMetadataService.merge(metadata, extraction)

    assert merged.extra == {"keep": "me"}


def test_merge_empty_extraction_is_noop():
    metadata = DocumentMetadata(title="t", author="a", extra={"k": 1})
    extraction = MetadataExtraction(source_type="pdf", values={}, extractor="<none>")

    merged = DocumentMetadataService.merge(metadata, extraction)

    assert merged == metadata


def test_merge_only_routes_unknown_keys_to_extra():
    metadata = DocumentMetadata()
    extraction = MetadataExtraction(
        source_type="pdf",
        values={"page_count": 10, "mime_type": "application/pdf"},
        extractor="fake",
    )

    merged = DocumentMetadataService.merge(metadata, extraction)

    assert merged.page_count == 10
    assert merged.mime_type == "application/pdf"
    assert merged.extra == {}


def test_register_extractor_public_alias():
    before = set(get_default_metadata_service().extractors)
    pdf = _FakeExtractor(("pdf",))

    register_extractor(pdf)

    after = get_default_metadata_service().extractors
    assert len(after) == len(before) + 1
    assert pdf in after


def test_get_default_metadata_service_is_singleton():
    assert get_default_metadata_service() is get_default_metadata_service()
