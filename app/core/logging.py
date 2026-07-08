"""Reusable application logging configuration."""

from __future__ import annotations

import json
import logging
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from app.core.config import LoggingSettings, Settings

_LOGGING_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Serialize log records as JSON for structured file output."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def setup_logging(settings: Settings, *, force: bool = False) -> None:
    """Configure console and file logging for the application."""

    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED and not force:
        return

    logging_settings = settings.logging
    environment = settings.app.environment.lower()
    debug_mode = _is_debug_mode(settings)

    root_logger = logging.getLogger()
    root_logger.setLevel(_resolve_level(logging_settings.level))
    root_logger.handlers.clear()

    if logging_settings.console_enabled:
        root_logger.addHandler(_build_console_handler(logging_settings, debug_mode))

    if logging_settings.file_enabled:
        root_logger.addHandler(_build_file_handler(settings.paths.log_root, logging_settings))

    root_logger.propagate = False
    logging.captureWarnings(True)

    application_logger = logging.getLogger("app")
    application_logger.debug(
        "Logging configured.",
        extra={
            "environment_name": environment,
            "debug_mode": debug_mode,
            "log_directory": str(settings.paths.log_root),
        },
    )

    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> Logger:
    """Return a named application logger."""

    return logging.getLogger(name)


def _build_console_handler(
    logging_settings: LoggingSettings,
    debug_mode: bool,
) -> logging.Handler:
    console = Console(no_color=not logging_settings.use_colors)
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=debug_mode,
        markup=False,
        rich_tracebacks=True,
        tracebacks_show_locals=debug_mode,
        log_time_format="[%Y-%m-%d %H:%M:%S]",
        omit_repeated_times=False,
    )
    rich_handler.setLevel(_resolve_level(logging_settings.level))
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    return rich_handler


def _build_file_handler(log_root: Path, logging_settings: LoggingSettings) -> logging.Handler:
    log_root.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=log_root / logging_settings.filename,
        maxBytes=logging_settings.max_bytes,
        backupCount=logging_settings.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(_resolve_level(logging_settings.level))

    if logging_settings.format == "json":
        file_handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"))
    else:
        file_handler.setFormatter(
            logging.Formatter(
                fmt=(
                    "%(asctime)s | %(levelname)s | %(name)s | %(module)s:%(lineno)d | "
                    "%(message)s"
                ),
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    return file_handler


def _resolve_level(level_name: str) -> int:
    return getattr(logging, level_name.upper())


def _is_debug_mode(settings: Settings) -> bool:
    return settings.app.environment.lower() == "development" or settings.logging.level == "DEBUG"
