"""Configuration loading and validation for the Personal AI Memory System."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    timeout_seconds: int = Field(default=120, ge=1)
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
    config_data["paths"] = _resolve_paths(config_data["paths"], project_root)

    config_data.setdefault("watcher", {})
    config_data["watcher"] = _resolve_watcher_paths(config_data["watcher"], project_root)

    config_data.setdefault("processing", {})
    config_data["processing"] = _resolve_processing_paths(
        config_data["processing"],
        project_root,
    )

    config_data.setdefault("queue", {})
    config_data["queue"] = _resolve_queue_paths(config_data["queue"], project_root)

    config_data.setdefault("manifest", {})
    config_data["manifest"] = _resolve_manifest_paths(config_data["manifest"], project_root)

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


def _resolve_paths(path_config: dict[str, Any], project_root: Path) -> dict[str, Path]:
    resolved_paths: dict[str, Path] = {}
    for key, value in path_config.items():
        if key == "project_root":
            resolved_paths[key] = project_root
            continue
        candidate = Path(value)
        resolved_paths[key] = (
            candidate if candidate.is_absolute() else (project_root / candidate).resolve()
        )
    return resolved_paths


def _resolve_watcher_paths(watcher_config: dict[str, Any], project_root: Path) -> dict[str, Any]:
    resolved_config = dict(watcher_config)
    for key in ("inbox_path", "processed_path", "failed_path"):
        if key not in resolved_config:
            continue
        candidate = Path(resolved_config[key])
        resolved_config[key] = (
            candidate if candidate.is_absolute() else (project_root / candidate).resolve()
        )
    return resolved_config


def _resolve_processing_paths(
    processing_config: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    resolved_config = dict(processing_config)
    for key in ("processed_path", "failed_path"):
        if key not in resolved_config:
            continue

        candidate = Path(resolved_config[key])
        resolved_config[key] = (
            candidate if candidate.is_absolute() else (project_root / candidate).resolve()
        )
    return resolved_config


def _resolve_queue_paths(queue_config: dict[str, Any], project_root: Path) -> dict[str, Any]:
    resolved_config = dict(queue_config)
    if "state_path" in resolved_config:
        candidate = Path(resolved_config["state_path"])
        resolved_config["state_path"] = (
            candidate if candidate.is_absolute() else (project_root / candidate).resolve()
        )
    return resolved_config


def _resolve_manifest_paths(
    manifest_config: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    resolved_config = dict(manifest_config)
    if "path" in resolved_config:
        candidate = Path(resolved_config["path"])
        resolved_config["path"] = (
            candidate if candidate.is_absolute() else (project_root / candidate).resolve()
        )
    return resolved_config


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
