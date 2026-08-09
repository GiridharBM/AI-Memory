"""P2-205: classifier language detection, prompt adaptation, and workflow propagation.

English default must stay byte-identical to the pre-P2-205 prompt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.application.ai_processor import DocumentAIProcessor
from app.domain.analysis import DocumentAnalysis, DocumentSummary
from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.processed_document import ProcessedDocument
from app.infrastructure.routing.classifier import DocumentClassifier
from app.pipelines.ingest_workflow import IngestionWorkflow
from app.prompts.document_analysis import build_document_analysis_user_prompt

FRENCH_TEXT = "Le chat et le chien sont dans le jardin, et la maison est grande."
GERMAN_TEXT = "Der Hund und die Katze sind im Garten, und das Haus ist groß."
JAPANESE_TEXT = "猫と犬が庭にいます。"


def _document(text: str = "# Hello\n\nWorld") -> SourceDocument:
    return SourceDocument(
        source="test.md",
        source_path=None,
        source_type="markdown",
        filename="test.md",
        text=text,
        metadata=DocumentMetadata(title="Test"),
    )


class TestClassifierLanguage:
    def test_french_detected_when_enabled(self) -> None:
        result = DocumentClassifier().classify(_document(FRENCH_TEXT))
        assert result.language == "fr"

    def test_german_detected_when_enabled(self) -> None:
        result = DocumentClassifier().classify(_document(GERMAN_TEXT))
        assert result.language == "de"

    def test_japanese_detected_when_enabled(self) -> None:
        result = DocumentClassifier().classify(_document(JAPANESE_TEXT))
        assert result.language == "ja"

    def test_disabled_returns_none(self) -> None:
        classifier = DocumentClassifier(language_detection_enabled=False)
        result = classifier.classify(_document(FRENCH_TEXT))
        assert result.language is None

    def test_default_matches_config_gate(self) -> None:
        from app.core.config import MetadataSettings

        assert MetadataSettings().language_detection_enabled is True
        assert DocumentClassifier()._language_enabled is True


class TestPromptAdaptation:
    _EXPECTED_EN_PROMPT = (
        "Analyze this source for a personal Obsidian knowledge base.\n"
        "\n"
        "Return only the structured JSON requested by the system prompt.\n"
        "\n"
        "Source metadata:\n"
        "- Source type: markdown\n"
        "- Filename: test.md\n"
        "- Source: test.md\n"
        "- Existing title: Test\n"
        "\n"
        "Source text:\n"
        '"""\n'
        "# Hello\n"
        "\n"
        "World\n"
        '"""'
    )

    def test_default_is_byte_identical_to_english(self) -> None:
        assert build_document_analysis_user_prompt(_document()) == self._EXPECTED_EN_PROMPT
        assert build_document_analysis_user_prompt(
            _document(), language="en",
        ) == self._EXPECTED_EN_PROMPT

    def test_french_appends_instruction(self) -> None:
        prompt = build_document_analysis_user_prompt(_document(), language="fr")
        assert prompt == self._EXPECTED_EN_PROMPT + "\n\nRespond in fr."

    def test_german_appends_instruction(self) -> None:
        prompt = build_document_analysis_user_prompt(_document(), language="de")
        assert prompt == self._EXPECTED_EN_PROMPT + "\n\nRespond in de."


class FakeOllamaClient:
    def __init__(self) -> None:
        self.requests: list[MagicMock] = []

    def generate_json(
        self, request: object, response_model: object, **kwargs: object,
    ) -> DocumentAnalysis:
        self.requests.append(MagicMock(prompt=request.prompt))
        return DocumentAnalysis(
            suggested_note_title="Test",
            summary=DocumentSummary(short="Short", detailed="Detailed"),
        )


class TestAiProcessorLanguage:
    def test_language_flows_into_prompt(self) -> None:
        client = FakeOllamaClient()
        processor = DocumentAIProcessor(client, language="fr")
        processor.process(_document())
        assert "Respond in fr." in client.requests[0].prompt

    def test_default_prompt_has_no_instruction(self) -> None:
        client = FakeOllamaClient()
        processor = DocumentAIProcessor(client)
        processor.process(_document())
        assert "Respond in" not in client.requests[0].prompt


class TestWorkflowPropagation:
    def test_routed_processor_sets_language(self, monkeypatch: object) -> None:
        import app.infrastructure.routing.processor_impls as impls

        captured: dict[str, ProcessedDocument] = {}

        class _FakeProcessor:
            def process(self, document: SourceDocument) -> ProcessedDocument:
                result = ProcessedDocument(title="t", content="c", markdown="m")
                captured["result"] = result
                return result

        monkeypatch.setattr(impls, "get_processor_by_name", lambda name: _FakeProcessor())  # type: ignore[attr-defined]

        workflow = _workflow()
        workflow._run_routed_processor("FakeProcessor", _document(), language="fr")
        assert captured["result"].language == "fr"

        workflow._run_routed_processor("FakeProcessor", _document(), language=None)
        assert captured["result"].language is None

    def test_run_passes_language_to_ai_processor(self, monkeypatch: object) -> None:
        import app.pipelines.ingest_workflow as wf_module

        captured: dict[str, object] = {}

        class _FakeAIProcessor:
            def __init__(
                self, client: object, *, model: str | None = None, language: str | None = None,
            ) -> None:
                captured["language"] = language
                self._model = model

            def process(self, document: SourceDocument) -> object:
                return MagicMock(
                    analysis=MagicMock(suggested_related_notes=[], suggested_backlinks=[]),
                )

        monkeypatch.setattr(wf_module, "DocumentAIProcessor", _FakeAIProcessor)

        workflow = _workflow()
        workflow._ingestion_service.ingest.return_value = MagicMock(
            succeeded=True, document=_document(FRENCH_TEXT), error=None,
        )
        def _stub(
            name: str, document: SourceDocument, language: str | None = None,
            parent_id: str | None = None, kind: str | None = None,
            requires_table_extraction: bool = False,
        ) -> tuple[SourceDocument, float | None, None]:
            return document, 0.9, None

        workflow._run_routed_processor = _stub  # type: ignore[method-assign]

        workflow.run("test.md")
        assert captured["language"] == "fr"


class TestWorkflowGateConfig:
    def test_enabled_detects_french(self, tmp_settings: object) -> None:
        workflow = _workflow(tmp_settings)
        assert workflow._classifier._language_enabled is True
        assert workflow._classifier.classify(_document(FRENCH_TEXT)).language == "fr"

    def test_disabled_keeps_language_none(self, tmp_settings: object) -> None:
        tmp_settings.intelligence.metadata.language_detection_enabled = False  # type: ignore[union-attr]
        workflow = _workflow(tmp_settings)
        assert workflow._classifier._language_enabled is False
        assert workflow._classifier.classify(_document(FRENCH_TEXT)).language is None


def _workflow(settings: object = None) -> IngestionWorkflow:
    return IngestionWorkflow(
        ingestion_service=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        settings=settings,
    )
