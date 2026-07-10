"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

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
