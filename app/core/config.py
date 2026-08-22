"""Configuration loading and validation for the Personal AI Memory System."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)

CONFIG_ENV_VAR = "PAM_ENVIRONMENT"
CONFIG_ENV_PREFIX = "PAM_"
DEFAULT_ENVIRONMENT = "development"
DEFAULT_CONFIG_DIRNAME = "config"
DEFAULT_CONFIG_FILENAME = "default.yaml"


class ConfigurationError(RuntimeError):
    """Raised when application configuration is invalid or cannot be loaded."""


class AppSettings(BaseModel):
    """Top-level application settings."""

    model_config = ConfigDict(extra="forbid")

    name: str = "personal-ai-memory"
    environment: str = DEFAULT_ENVIRONMENT


class PathSettings(BaseModel):
    """Filesystem paths used by the application."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    vault_root: Path
    inbox_root: Path
    staging_root: Path
    manifest_root: Path
    cache_root: Path
    log_root: Path

    @field_validator(
        "project_root",
        "vault_root",
        "inbox_root",
        "staging_root",
        "manifest_root",
        "cache_root",
        "log_root",
        mode="before",
    )
    @classmethod
    def _coerce_path(cls, value: str | Path) -> Path:
        return Path(value)


class OllamaSettings(BaseModel):
    """Settings for the local Ollama runtime."""

    model_config = ConfigDict(extra="forbid")

    host: HttpUrl = Field(default_factory=lambda: HttpUrl("http://localhost:11434"))
    model: str = "qwen3:8b"
    timeout_seconds: int = Field(default=300, ge=1)
    request_retries: int = Field(default=3, ge=0)
    retry_backoff_seconds: float = Field(default=1.0, ge=0.0)


class LoggingSettings(BaseModel):
    """Settings for application logging."""

    model_config = ConfigDict(extra="forbid")

    level: str = "INFO"
    format: str = "console"
    console_enabled: bool = True
    file_enabled: bool = True
    use_colors: bool = True
    filename: str = "application.log"
    max_bytes: int = Field(default=10_485_760, ge=1024)
    backup_count: int = Field(default=5, ge=1)

    @field_validator("level")
    @classmethod
    def _validate_level(cls, value: str) -> str:
        allowed_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        normalized = value.upper()
        if normalized not in allowed_levels:
            raise ValueError(
                f"Unsupported logging level '{value}'. Expected one of: {sorted(allowed_levels)}."
            )
        return normalized

    @field_validator("format")
    @classmethod
    def _validate_format(cls, value: str) -> str:
        allowed_formats = {"console", "json"}
        normalized = value.lower()
        if normalized not in allowed_formats:
            raise ValueError(
                f"Unsupported logging format '{value}'. Expected one of: {sorted(allowed_formats)}."
            )
        return normalized


class WatcherSettings(BaseModel):
    """Settings for the inbox folder watcher."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    inbox_path: Path = Field(default_factory=lambda: Path("./data/inbox"))
    processed_path: Path = Field(default_factory=lambda: Path("./data/processed"))
    failed_path: Path = Field(default_factory=lambda: Path("./data/failed"))
    recursive: bool = True
    interval_seconds: float = Field(default=1.0, ge=0.1)
    supported_extensions: list[str] = Field(default_factory=lambda: [".md"])

    @field_validator("inbox_path", "processed_path", "failed_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: str | Path) -> Path:
        return Path(value)

    @field_validator("supported_extensions")
    @classmethod
    def _normalize_extensions(cls, value: list[str]) -> list[str]:
        normalized = []
        for extension in value:
            candidate = extension.lower()
            if not candidate.startswith("."):
                candidate = f".{candidate}"
            normalized.append(candidate)
        return normalized


class QueueSettings(BaseModel):
    """Settings for the file processing queue."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    workers: int = Field(default=1, ge=1, le=1)
    max_size: int = Field(default=1000, ge=1)
    state_path: Path = Field(default_factory=lambda: Path("./data/manifests/queue_state.json"))

    @field_validator("state_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: str | Path) -> Path:
        return Path(value)


class ManifestSettings(BaseModel):
    """Settings for the processed file manifest."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    path: Path = Field(default_factory=lambda: Path("./data/manifests/processed_files.json"))

    @field_validator("path", mode="before")
    @classmethod
    def _coerce_path(cls, value: str | Path) -> Path:
        return Path(value)


class ProcessingSettings(BaseModel):
    """Settings for post-processing file movement."""

    model_config = ConfigDict(extra="forbid")

    move_processed: bool = True
    move_failed: bool = True
    processed_path: Path = Field(default_factory=lambda: Path("./data/processed"))
    failed_path: Path = Field(default_factory=lambda: Path("./data/failed"))

    @field_validator("processed_path", "failed_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: str | Path) -> Path:
        return Path(value)


class ModelRoutingSettings(BaseModel):
    """Settings for multi-model routing by content type."""

    model_config = ConfigDict(extra="forbid")

    general_text: str = "qwen3:8b"
    programming: str = "qwen2.5-coder:7b"
    vision: str = "qwen2.5vl:latest"
    handwriting_ocr: str = "qwen2.5vl:latest"
    scanned_ocr: str = "qwen2.5vl:latest"
    audio: str = "faster-whisper"
    embeddings: str = "nomic-embed-text"

    def model_for(self, key: str) -> str:
        """Return the model name for a routing key, falling back to general_text."""
        if not hasattr(self, key):
            _logger.warning("Unknown routing key '%s', falling back to general_text.", key)
        return getattr(self, key, self.general_text)


class PromptSettings(BaseModel):
    """Prompt templates for vision/OCR processors (R-6).

    Defaults are byte-identical to the Phase-1 hardcoded prompts. Templates may
    contain a ``{language}`` slot substituted by the processor's prompt
    resolver; the shipped defaults carry no slot so the default prompt matches
    Phase 1 exactly.
    """

    model_config = ConfigDict(extra="forbid")

    ocr: str = (
        "This is a scanned PDF page. Extract all visible text accurately. "
        "Return only the extracted text, nothing else."
    )
    handwriting: str = (
        "This is a handwritten document. Transcribe all handwritten text "
        "as accurately as possible. Return only the transcribed text, "
        "nothing else."
    )
    vision: str = (
        "Analyze this image. If it contains handwritten text, transcribe "
        "all handwritten text accurately. If it contains printed text or "
        "digital content, extract all visible text. Return only the "
        "extracted text, nothing else."
    )


class OcrSettings(BaseModel):
    """Settings for the OCR engine subsystem (P2-108).

    Defaults reproduce Phase 1: ``engine="auto"`` (vision primary, Tesseract
    fallback), ``page_limit=5`` (hardcoded Phase-1 cap), ``zoom=2.0``.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    engine: Literal["auto", "vision", "tesseract"] = "auto"
    page_limit: int = Field(default=5, ge=0)  # 0 = all pages
    zoom: float = Field(default=2.0, gt=0)
    preprocess: bool = False
    tesseract_cmd: str = ""  # empty => look up on PATH
    tesseract_lang: str = "eng"
    confidence_threshold: float = Field(default=0.0, ge=0.0)
    max_pages: int = Field(default=200, ge=1)


class HookChainSettings(BaseModel):
    """Named plugin lists for the ingestion hook chain (P2-206)."""

    model_config = ConfigDict(extra="forbid")

    pre: list[str] = Field(default_factory=list)
    post: list[str] = Field(default_factory=list)


class MetadataSettings(BaseModel):
    """Settings for the metadata extraction framework (Milestone 2.2).

    ``enabled: false`` returns Phase-1-identical documents (rollback R-4).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    extractors: str = "default"
    mime_enabled: bool = True
    language_detection_enabled: bool = True
    max_file_size_mb: int = Field(default=50, ge=1)
    url_timeout_seconds: int = Field(default=30, ge=1)
    email_attachments: bool = True
    max_attachments: int = Field(default=20, ge=1)
    hooks: HookChainSettings = Field(default_factory=HookChainSettings)


class StructureSettings(BaseModel):
    """Settings for document structure analysis (Milestone 2.3).

    ``enabled: false`` returns M2.2-identical documents (rollback R-4).
    ``enrich_analysis_input`` is a contract-only field (frozen §7 / C-5):
    declared for the future structure-aware-prompting contract, not read by
    any code this milestone.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    enrich_analysis_input: bool = False


class EntitySettings(BaseModel):
    """Settings for entity extraction (P4-102).

    ``enabled: false`` returns M2.2-identical documents (no ``entities`` key;
    rollback R-4). Extraction is deterministic and offline; no external service
    is gated by this toggle, only the enrichment attachment point.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class RelationshipSettings(BaseModel):
    """Settings for relationship detection (P4-103).

    ``enabled: false`` omits the ``relationships`` enrichment key (rollback
    R-4). Detection consumes extracted entities (P4-102) and is deterministic
    and offline; no external service is gated by this toggle, only the
    enrichment attachment point.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class GraphSettings(BaseModel):
    """Settings for document-level knowledge graph construction (P4-104).

    ``enabled: false`` omits the ``knowledge_graph`` enrichment key (rollback
    R-4). Construction consumes the extracted entities (P4-102) and detected
    relationships (P4-103) into an in-memory ``KnowledgeGraph``; it is
    deterministic and offline, and no external service or persistent
    graph-database infrastructure is gated by this toggle.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class TableSettings(BaseModel):
    """Settings for table intelligence (Milestone 2.4).

    ``enabled: false`` restores Phase-1 note output exactly (rollback R-4);
    ``max_rows``/``max_cols`` bound extraction (frozen §2.4). The frozen
    §2.4 ``min_confidence`` key was removed — pdfplumber exposes no per-table
    confidence to gate on (review R1, deviation recorded).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    pdf_engine: str = "pdfplumber"
    max_rows: int = Field(default=200, ge=1)
    max_cols: int = Field(default=30, ge=1)
    header_sniffing: bool = True


class ImageSettings(BaseModel):
    """Settings for image intelligence (Milestone 2.5).

    ``preprocess`` controls the shared preprocess module on the image-analysis
    path (R-a); the OCR path keeps its own ``OcrSettings.preprocess`` toggle —
    one shared ``imaging/preprocess.py`` implementation, two toggles.
    ``exif_enabled`` / ``diagram_enabled`` gate the additive EXIF and drawio
    features (R-4). ``max_dimensions``/``max_bytes`` bound preprocessing;
    ``max_dimensions`` (scalar max edge or ``[width, height]``) supersedes the
    historical ``MAX_EDGE = 8000`` constant (P2-503, frozen §4.5 ``[8192, 8192]``).
    """

    model_config = ConfigDict(extra="forbid")

    preprocess: bool = False
    exif_enabled: bool = True
    diagram_enabled: bool = True
    max_dimensions: int | tuple[int, int] = (8192, 8192)
    max_bytes: int = Field(default=20 * 1024 * 1024, ge=1)


class CodeSettings(BaseModel):
    """Settings for code & notebook intelligence (Milestone 2.6).

    ``enabled: false`` restores Phase-1 behavior exactly: code passthrough and
    notebook flattening with no ``code_structure``/``notebook_structure`` keys
    (rollback R-4). ``languages="default"`` selects the built-in
    ``extensions.py`` suffix-to-language mapping; other values are not
    supported in M2.6 (extensibility deferred). ``max_code_chars`` is a Python
    ``str`` length — oversized sources are truncated at parse time with a
    logged warning (frozen §4.6 performance). ``max_cell_outputs`` caps
    notebook cell outputs during ``NotebookParser.parse()`` (entries beyond
    the cap replaced with a ``[truncated]`` marker). ``include_docstrings``
    is a contract-only field this milestone (C-5 precedent): declared for the
    future structure-consuming phase, not read by any code.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    languages: Literal["default"] = "default"
    max_cell_outputs: int = Field(default=10, ge=1)
    max_code_chars: int = Field(default=100000, ge=1)
    include_docstrings: bool = True


class RerankerSettings(BaseModel):
    """Settings for the cross-encoder reranker (Phase 3C).

    The reranker is an enhancement, not a requirement.  When ``enabled=false``
    or when the model is unavailable, the system falls back to RRF ordering
    (Phase 3B behavior).  The ``min_score`` field is the gate threshold for
    cross-encoder relevance scores (a different score space than cosine).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    top_n: int = Field(default=20, ge=1)
    device: str = "cpu"
    timeout_seconds: float = Field(default=5.0, gt=0)
    min_score: float = Field(default=0.0, ge=0.0)


class HydeSettings(BaseModel):
    """Settings for Hypothetical Document Embedding (HyDE, Phase 3E).

    When ``enabled=true``, queries are transformed into hypothetical answer
    paragraphs before embedding, while the original query text is used for
    BM25.  If the LLM call fails, the original query embedding is used.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_length: int = Field(default=500, ge=50)
    timeout_seconds: float = Field(default=30.0, gt=0)


class ChunkingSettings(BaseModel):
    """Settings for the semantic chunker (P3-105, P3-205).

    ``sentence_tokenizer`` selects the sentence engine: ``"auto"`` (default)
    reproduces post-P3-104 behavior — NLTK ``punkt_tab`` when available,
    stdlib heuristic fallback otherwise (D4/D8); ``"heuristic"`` forces the
    deterministic stdlib engine; ``"nltk"`` forces the NLTK engine (failing
    fast if its data is missing).

    The policy fields are the adaptive chunking knobs (P3-205); their defaults
    mirror :class:`ChunkingPolicy`, reproducing P3-204 output.
    """

    model_config = ConfigDict(extra="forbid")

    sentence_tokenizer: Literal["auto", "nltk", "heuristic"] = "auto"
    heading_size_step: int = Field(default=0, ge=0)
    min_chunk_chars: int = Field(default=200, ge=1)
    snap_overlap: bool = False
    snap_max_back: int = Field(default=2000, ge=0)
    heading_overlap_boundary: bool = False


class IntelligenceSettings(BaseModel):
    """Settings for the intelligence subsystem (OCR engine, prompt templates)."""

    model_config = ConfigDict(extra="forbid")

    ocr: OcrSettings = Field(default_factory=OcrSettings)
    prompts: PromptSettings = Field(default_factory=PromptSettings)
    metadata: MetadataSettings = Field(default_factory=MetadataSettings)
    structure: StructureSettings = Field(default_factory=StructureSettings)
    entities: EntitySettings = Field(default_factory=EntitySettings)
    relationships: RelationshipSettings = Field(default_factory=RelationshipSettings)
    graph: GraphSettings = Field(default_factory=GraphSettings)
    tables: TableSettings = Field(default_factory=TableSettings)
    images: ImageSettings = Field(default_factory=ImageSettings)
    code: CodeSettings = Field(default_factory=CodeSettings)


class Settings(BaseSettings):
    """Validated application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="PAM_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    app: AppSettings
    paths: PathSettings
    ollama: OllamaSettings
    logging: LoggingSettings
    watcher: WatcherSettings = Field(default_factory=WatcherSettings)
    queue: QueueSettings = Field(default_factory=QueueSettings)
    manifest: ManifestSettings = Field(default_factory=ManifestSettings)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)
    models: ModelRoutingSettings = Field(default_factory=ModelRoutingSettings)
    intelligence: IntelligenceSettings = Field(default_factory=IntelligenceSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    hyde: HydeSettings = Field(default_factory=HydeSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)


def load_settings(
    *,
    environment: str | None = None,
    config_dir: Path | None = None,
) -> Settings:
    """Load, merge, and validate YAML and environment-based configuration."""

    project_root = _discover_project_root()
    resolved_config_dir = (config_dir or project_root / DEFAULT_CONFIG_DIRNAME).resolve()
    resolved_environment = environment or os.getenv(CONFIG_ENV_VAR) or DEFAULT_ENVIRONMENT

    default_config_path = resolved_config_dir / DEFAULT_CONFIG_FILENAME
    environment_config_path = resolved_config_dir / f"{resolved_environment}.yaml"

    config_data = _load_yaml_file(default_config_path)
    if environment_config_path.exists():
        config_data = _merge_dicts(config_data, _load_yaml_file(environment_config_path))

    config_data = _apply_environment_overrides(config_data)

    config_data.setdefault("app", {})
    config_data["app"]["environment"] = resolved_environment

    config_data.setdefault("paths", {})
    config_data["paths"]["project_root"] = project_root
    config_data["paths"] = _resolve_relative_paths(
        config_data["paths"],
        {"vault_root", "inbox_root", "staging_root", "manifest_root", "cache_root", "log_root"},
        project_root,
    )

    config_data.setdefault("watcher", {})
    config_data["watcher"] = _resolve_relative_paths(
        config_data["watcher"],
        {"inbox_path", "processed_path", "failed_path"},
        project_root,
    )

    config_data.setdefault("processing", {})
    config_data["processing"] = _resolve_relative_paths(
        config_data["processing"],
        {"processed_path", "failed_path"},
        project_root,
    )

    config_data.setdefault("queue", {})
    config_data["queue"] = _resolve_relative_paths(
        config_data["queue"],
        {"state_path"},
        project_root,
    )

    config_data.setdefault("manifest", {})
    config_data["manifest"] = _resolve_relative_paths(
        config_data["manifest"],
        {"path"},
        project_root,
    )

    config_data.setdefault("models", {})

    try:
        return Settings(**config_data)
    except ValidationError as exc:
        raise ConfigurationError(f"Configuration validation failed:\n{exc}") from exc


def _discover_project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise ConfigurationError("Unable to determine the project root from the current file path.")


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Failed to parse YAML configuration file: {path}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Configuration file must contain a mapping at the top level: {path}"
        )

    return data


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_relative_paths(
    config: dict[str, Any],
    keys: set[str],
    project_root: Path,
) -> dict[str, Any]:
    resolved = dict(config)
    for key in keys:
        if key not in resolved:
            continue
        candidate = Path(resolved[key])
        resolved[key] = (
            candidate if candidate.is_absolute() else (project_root / candidate).resolve()
        )
    return resolved


def _apply_environment_overrides(config_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(config_data)
    for key, value in os.environ.items():
        if not key.startswith(CONFIG_ENV_PREFIX) or key == CONFIG_ENV_VAR:
            continue

        path = key[len(CONFIG_ENV_PREFIX) :].lower().split("__")
        if not path or any(not segment for segment in path):
            continue

        _set_nested_value(merged, path, _parse_environment_value(value))

    return merged


def _set_nested_value(target: dict[str, Any], path: list[str], value: Any) -> None:
    current = target
    for segment in path[:-1]:
        existing = current.get(segment)
        if not isinstance(existing, dict):
            existing = {}
            current[segment] = existing
        current = existing
    current[path[-1]] = value


def _parse_environment_value(value: str) -> Any:
    parsed = yaml.safe_load(value)
    return value if parsed is None and value.lower() != "null" else parsed
