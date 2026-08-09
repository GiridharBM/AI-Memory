"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import ConfigurationError, load_settings


def test_load_settings_resolves_default_paths() -> None:
    settings = load_settings()

    assert settings.app.environment == "development"
    assert settings.ollama.model == "qwen3:8b"
    assert settings.paths.vault_root.is_absolute()
    assert settings.paths.vault_root == settings.paths.project_root / "vault"


def test_environment_variables_override_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAM_OLLAMA__MODEL", "test-model")
    monkeypatch.setenv("PAM_LOGGING__LEVEL", "ERROR")
    monkeypatch.setenv("PAM_PATHS__VAULT_ROOT", "D:\\TestVault")
    monkeypatch.setenv("PAM_WATCHER__ENABLED", "false")
    monkeypatch.setenv("PAM_WATCHER__INTERVAL_SECONDS", "2")
    monkeypatch.setenv("PAM_WATCHER__RECURSIVE", "false")

    settings = load_settings()

    assert settings.ollama.model == "test-model"
    assert settings.logging.level == "ERROR"
    assert settings.paths.vault_root == Path("D:\\TestVault")
    assert settings.watcher.enabled is False
    assert settings.watcher.interval_seconds == 2
    assert settings.watcher.recursive is False


def test_production_environment_separates_logging_defaults() -> None:
    settings = load_settings(environment="production")

    assert settings.app.environment == "production"
    assert settings.logging.level == "INFO"
    assert settings.logging.format == "json"
    assert settings.logging.use_colors is False


def test_intelligence_prompts_defaults_are_phase1_prompts() -> None:
    settings = load_settings()

    assert settings.intelligence.prompts.ocr == (
        "This is a scanned PDF page. Extract all visible text accurately. "
        "Return only the extracted text, nothing else."
    )
    assert settings.intelligence.prompts.handwriting.startswith(
        "This is a handwritten document."
    )
    assert settings.intelligence.prompts.vision.startswith("Analyze this image.")


def test_intelligence_ocr_defaults_reproduce_phase1() -> None:
    settings = load_settings()

    ocr = settings.intelligence.ocr
    assert ocr.enabled is True
    assert ocr.engine == "auto"
    assert ocr.page_limit == 5
    assert ocr.zoom == 2.0
    assert ocr.preprocess is False
    assert ocr.tesseract_cmd == ""
    assert ocr.tesseract_lang == "eng"
    assert ocr.confidence_threshold == 0.0
    assert ocr.max_pages == 200


def test_intelligence_ocr_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAM_INTELLIGENCE__OCR__PAGE_LIMIT", "3")
    monkeypatch.setenv("PAM_INTELLIGENCE__OCR__ENGINE", "tesseract")
    monkeypatch.setenv("PAM_INTELLIGENCE__OCR__ENABLED", "false")

    settings = load_settings()

    assert settings.intelligence.ocr.page_limit == 3
    assert settings.intelligence.ocr.engine == "tesseract"
    assert settings.intelligence.ocr.enabled is False


def test_intelligence_tables_defaults_reproduce_frozen_spec() -> None:
    settings = load_settings()

    tables = settings.intelligence.tables
    assert tables.enabled is True
    assert tables.pdf_engine == "pdfplumber"
    assert tables.max_rows == 200
    assert tables.max_cols == 30
    assert tables.header_sniffing is True


def test_intelligence_tables_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAM_INTELLIGENCE__TABLES__ENABLED", "false")
    monkeypatch.setenv("PAM_INTELLIGENCE__TABLES__PDF_ENGINE", "camelot")
    monkeypatch.setenv("PAM_INTELLIGENCE__TABLES__MAX_ROWS", "50")

    settings = load_settings()

    assert settings.intelligence.tables.enabled is False
    assert settings.intelligence.tables.pdf_engine == "camelot"
    assert settings.intelligence.tables.max_rows == 50


def test_intelligence_images_defaults_reproduce_frozen_spec() -> None:
    settings = load_settings()

    images = settings.intelligence.images
    assert images.preprocess is False
    assert images.exif_enabled is True
    assert images.diagram_enabled is True
    assert images.max_dimensions == (8192, 8192)
    assert images.max_bytes == 20 * 1024 * 1024


def test_intelligence_images_accepts_scalar_or_pair_dim_guard() -> None:
    from app.core.config import ImageSettings

    settings = load_settings()
    images = settings.intelligence.images

    # Tuple-pair guard (frozen §4.5 [8192, 8192]).
    assert images.max_dimensions == (8192, 8192)

    # A scalar int is also accepted (single max-edge cap).
    images.max_dimensions = 4096
    assert images.max_dimensions == 4096

    # A list (as YAML/JSON round-trips produce) is stored/parsed as a pair.
    images.max_dimensions = [1000, 2000]
    assert images.max_dimensions == [1000, 2000]

    # Invalid shapes are rejected at construction/parse time.
    with pytest.raises(ValidationError):
        ImageSettings(max_dimensions="wide")


def test_intelligence_images_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAM_INTELLIGENCE__IMAGES__PREPROCESS", "true")
    monkeypatch.setenv("PAM_INTELLIGENCE__IMAGES__EXIF_ENABLED", "false")
    monkeypatch.setenv("PAM_INTELLIGENCE__IMAGES__DIAGRAM_ENABLED", "false")
    monkeypatch.setenv("PAM_INTELLIGENCE__IMAGES__MAX_DIMENSIONS", "4096")
    monkeypatch.setenv("PAM_INTELLIGENCE__IMAGES__MAX_BYTES", "1024")

    settings = load_settings()

    images = settings.intelligence.images
    assert images.preprocess is True
    assert images.exif_enabled is False
    assert images.diagram_enabled is False
    assert images.max_dimensions == 4096
    assert images.max_bytes == 1024


def test_intelligence_code_defaults_reproduce_frozen_spec() -> None:
    from app.core.config import CodeSettings

    settings = load_settings()
    code = settings.intelligence.code
    assert code == CodeSettings()
    assert code.enabled is True
    assert code.languages == "default"
    assert code.max_cell_outputs == 10
    assert code.max_code_chars == 100000
    assert code.include_docstrings is True


def test_intelligence_settings_has_code() -> None:
    from app.core.config import CodeSettings, IntelligenceSettings

    settings = IntelligenceSettings()
    assert isinstance(settings.code, CodeSettings)


def test_intelligence_code_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAM_INTELLIGENCE__CODE__ENABLED", "false")
    monkeypatch.setenv("PAM_INTELLIGENCE__CODE__MAX_CELL_OUTPUTS", "3")
    monkeypatch.setenv("PAM_INTELLIGENCE__CODE__MAX_CODE_CHARS", "5000")

    settings = load_settings()

    code = settings.intelligence.code
    assert code.enabled is False
    assert code.max_cell_outputs == 3
    assert code.max_code_chars == 5000


def test_intelligence_ocr_unknown_engine_fails_fast(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
app:
  name: personal-ai-memory
paths:
  vault_root: ./vault
  inbox_root: ./data/inbox
  staging_root: ./data/staging
  manifest_root: ./data/manifests
  cache_root: ./data/cache
  log_root: ./data/logs
intelligence:
  ocr:
    engine: bogus
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_settings(config_dir=config_dir)


def test_chunking_defaults_reproduce_frozen_spec() -> None:
    from app.core.config import ChunkingSettings

    settings = load_settings()

    assert settings.chunking == ChunkingSettings()
    assert settings.chunking.sentence_tokenizer == "auto"


def test_chunking_sentence_tokenizer_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAM_CHUNKING__SENTENCE_TOKENIZER", "heuristic")

    settings = load_settings()

    assert settings.chunking.sentence_tokenizer == "heuristic"


def test_chunking_policy_fields_reproduce_frozen_spec() -> None:
    from app.core.config import ChunkingSettings

    settings = load_settings()

    assert settings.chunking.heading_size_step == ChunkingSettings().heading_size_step
    assert settings.chunking.min_chunk_chars == 200
    assert settings.chunking.snap_overlap is False
    assert settings.chunking.snap_max_back == 2000
    assert settings.chunking.heading_overlap_boundary is False


def test_chunking_policy_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAM_CHUNKING__HEADING_SIZE_STEP", "500")
    monkeypatch.setenv("PAM_CHUNKING__MIN_CHUNK_CHARS", "300")
    monkeypatch.setenv("PAM_CHUNKING__SNAP_OVERLAP", "true")
    monkeypatch.setenv("PAM_CHUNKING__HEADING_OVERLAP_BOUNDARY", "true")

    settings = load_settings()

    assert settings.chunking.heading_size_step == 500
    assert settings.chunking.min_chunk_chars == 300
    assert settings.chunking.snap_overlap is True
    assert settings.chunking.heading_overlap_boundary is True


def test_chunking_invalid_sentence_tokenizer_fails_fast(tmp_path: Path) -> None:
    from app.core.config import ChunkingSettings

    with pytest.raises(ValidationError):
        ChunkingSettings(sentence_tokenizer="bogus")

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
app:
  name: personal-ai-memory
paths:
  vault_root: ./vault
  inbox_root: ./data/inbox
  staging_root: ./data/staging
  manifest_root: ./data/manifests
  cache_root: ./data/cache
  log_root: ./data/logs
chunking:
  sentence_tokenizer: bogus
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_settings(config_dir=config_dir)


def test_invalid_config_fails_fast(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
app:
  name: personal-ai-memory
paths:
  vault_root: ./vault
  inbox_root: ./data/inbox
  staging_root: ./data/staging
  manifest_root: ./data/manifests
  cache_root: ./data/cache
  log_root: ./data/logs
ollama:
  timeout_seconds: 0
logging:
  level: LOUD
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_settings(config_dir=config_dir)
