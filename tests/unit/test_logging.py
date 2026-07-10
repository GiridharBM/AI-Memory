"""Tests for reusable logging setup."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.config import AppSettings, LoggingSettings, OllamaSettings, PathSettings, Settings
from app.core.logging import get_logger, setup_logging


def test_setup_logging_writes_rotating_file(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    setup_logging(settings, force=True)
    logger = get_logger("app.tests.logging")
    logger.info("hello logging")

    log_file = tmp_path / "logs" / "test.log"
    assert log_file.exists()
    assert "hello logging" in log_file.read_text(encoding="utf-8")


def test_setup_logging_supports_json_file_format(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        logging_settings=LoggingSettings(
            level="INFO",
            format="json",
            console_enabled=False,
            file_enabled=True,
            filename="json.log",
        ),
    )

    setup_logging(settings, force=True)
    logging.getLogger("app.tests.json").warning("json message")

    log_lines = (tmp_path / "logs" / "json.log").read_text(encoding="utf-8").splitlines()
    log_line = log_lines[-1]
    payload = json.loads(log_line)
    assert payload["level"] == "WARNING"
    assert payload["message"] == "json message"


def test_setup_logging_writes_component_logs(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        logging_settings=LoggingSettings(
            level="INFO",
            format="console",
            console_enabled=False,
            file_enabled=True,
            filename="application.log",
        ),
    )

    setup_logging(settings, force=True)
    logging.getLogger("app.watcher.service").info("Watcher started")
    logging.getLogger("app.queue.worker").info("Processing python.md")
    logging.getLogger("app.infrastructure.llm.ollama_client").error("Ollama timeout")

    assert "Watcher started" in (tmp_path / "logs" / "watcher.log").read_text(encoding="utf-8")
    assert "Processing python.md" in (tmp_path / "logs" / "processing.log").read_text(
        encoding="utf-8"
    )
    assert "Ollama timeout" in (tmp_path / "logs" / "errors.log").read_text(encoding="utf-8")
    application_log = (tmp_path / "logs" / "application.log").read_text(encoding="utf-8")
    assert "Application started" in application_log
    assert "Configuration loaded" in application_log


def _settings(
    tmp_path: Path,
    *,
    logging_settings: LoggingSettings | None = None,
) -> Settings:
    return Settings(
        app=AppSettings(name="personal-ai-memory", environment="development"),
        paths=PathSettings(
            project_root=tmp_path,
            vault_root=tmp_path / "vault",
            inbox_root=tmp_path / "inbox",
            staging_root=tmp_path / "staging",
            manifest_root=tmp_path / "manifests",
            cache_root=tmp_path / "cache",
            log_root=tmp_path / "logs",
        ),
        ollama=OllamaSettings(),
        logging=logging_settings
        or LoggingSettings(
            level="INFO",
            format="console",
            console_enabled=False,
            file_enabled=True,
            filename="test.log",
        ),
    )
