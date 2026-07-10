"""CLI entrypoint for the Personal AI Memory System."""

from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.json import JSON as RichJSON
from rich.panel import Panel
from rich.table import Table

from app.application import AIProcessingError
from app.core.config import ConfigurationError, Settings, load_settings
from app.core.logging import get_logger, setup_logging
from app.infrastructure.llm import OllamaClient, OllamaClientError
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow, IngestionWorkflowError
from app.queue import QueueStateStore
from app.watcher import WatchService

cli = typer.Typer(
    add_completion=False,
    help="Local-first tooling for the Personal AI Memory System.",
    no_args_is_help=True,
)
ingest_cli = typer.Typer(help="Ingest sources into the Obsidian wiki.", no_args_is_help=True)
cli.add_typer(ingest_cli, name="ingest")

console = Console()
logger = get_logger(__name__)

PdfPathArgument = Annotated[
    Path,
    typer.Argument(
        help="Path to a PDF file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
]
MarkdownPathArgument = Annotated[
    Path,
    typer.Argument(
        help="Path to a Markdown file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
]
TxtPathArgument = Annotated[
    Path,
    typer.Argument(
        help="Path to a TXT file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
]
GitHubUrlArgument = Annotated[str, typer.Argument(help="GitHub repository URL.")]
YouTubeUrlArgument = Annotated[str, typer.Argument(help="YouTube video URL.")]
EnvironmentOption = Annotated[
    str | None,
    typer.Option(
        "--environment",
        "-e",
        help="Configuration environment to load.",
    ),
]
ConfigJsonOption = Annotated[
    bool,
    typer.Option("--json", help="Print raw JSON configuration."),
]


@ingest_cli.command("pdf")
def ingest_pdf(path: PdfPathArgument) -> None:
    """Ingest a PDF file."""

    _run_ingest(path, expected_source_type="pdf")


@ingest_cli.command("markdown")
def ingest_markdown(path: MarkdownPathArgument) -> None:
    """Ingest a Markdown file."""

    _run_ingest(path, expected_source_type="markdown")


@ingest_cli.command("txt")
def ingest_txt(path: TxtPathArgument) -> None:
    """Ingest a plain text file."""

    _run_ingest(path, expected_source_type="text")


@ingest_cli.command("github")
def ingest_github(url: GitHubUrlArgument) -> None:
    """Ingest a GitHub repository README."""

    _run_ingest(url, expected_source_type="github_readme")


@ingest_cli.command("youtube")
def ingest_youtube(url: YouTubeUrlArgument) -> None:
    """Ingest a YouTube video transcript."""

    _run_ingest(url, expected_source_type="youtube_transcript")


@cli.command("status")
def status() -> None:
    """Show local project and vault status."""

    settings = _load_configured_settings()
    setup_logging(settings)
    logger.info("Status requested")
    _ensure_runtime_directories(settings)

    vault_root = settings.paths.vault_root
    notes_root = vault_root / "Notes"
    note_count = len(list(notes_root.glob("*.md"))) if notes_root.exists() else 0
    manifest_entries = ManifestManager(
        settings.manifest.path,
        project_root=settings.paths.project_root,
        enabled=settings.manifest.enabled,
    ).count()
    pending_queue_items = len(QueueStateStore(settings.queue.state_path).load())
    ollama_status = _ollama_status(settings)
    vault_status = "Connected" if _is_writable_directory(vault_root) else "Not writable"

    table = Table(title="AI Memory Status", show_header=True, header_style="bold")
    table.add_column("Area")
    table.add_column("Status")
    table.add_column("Details")
    table.add_row("Watcher", _healthy("Configured" if settings.watcher.enabled else "Disabled"), "")
    table.add_row(
        "Inbox",
        _healthy("Ready"),
        _display_path(settings.watcher.inbox_path, settings.paths.project_root),
    )
    table.add_row("Queue", _healthy("Enabled" if settings.queue.enabled else "Disabled"), "")
    table.add_row("Items waiting", _healthy(str(pending_queue_items)), "")
    table.add_row("Manifest entries", _healthy(str(manifest_entries)), "")
    table.add_row("Processed today", _healthy("0"), "Runtime counter resets on restart")
    table.add_row("Skipped duplicates", _healthy("0"), "Runtime counter resets on restart")
    table.add_row("Failed today", _healthy("0"), "Runtime counter resets on restart")
    table.add_row("Ollama", _status_style(ollama_status), str(settings.ollama.host))
    table.add_row("Model", settings.ollama.model, "")
    table.add_row("Vault", _status_style(vault_status), str(vault_root))
    table.add_row("Generated notes", _healthy(str(note_count)), "")
    table.add_row("Logs", _healthy("Ready"), str(settings.paths.log_root))
    console.print(table)

@cli.command("doctor")
def doctor() -> None:
    """Check local configuration, dependencies, folders, and Ollama availability."""

    checks = Table(title="Doctor", show_header=True, header_style="bold")
    checks.add_column("Check")
    checks.add_column("Status")
    checks.add_column("Details")

    exit_code = 0

    try:
        settings = _load_configured_settings()
        setup_logging(settings)
        checks.add_row("Configuration", "OK", settings.app.environment)
    except Exception as exc:
        checks.add_row("Configuration", "FAIL", str(exc))
        console.print(checks)
        raise typer.Exit(1) from exc

    required_modules = [
        "ollama",
        "pydantic",
        "pydantic_settings",
        "pypdf",
        "rich",
        "typer",
        "yaml",
        "youtube_transcript_api",
    ]
    for module_name in required_modules:
        if find_spec(module_name) is None:
            checks.add_row(f"Dependency {module_name}", "FAIL", "Not installed")
            exit_code = 1
        else:
            checks.add_row(f"Dependency {module_name}", "OK", "Installed")

    checks.add_row("Python", "OK", f"{sys.version_info.major}.{sys.version_info.minor}")

    for label, path in [
        ("Project root", settings.paths.project_root),
        ("Vault root", settings.paths.vault_root),
        ("Data inbox", settings.paths.inbox_root),
        ("Processed", settings.processing.processed_path),
        ("Failed", settings.processing.failed_path),
        ("Manifest root", settings.paths.manifest_root),
        ("Log root", settings.paths.log_root),
        ("Cache root", settings.paths.cache_root),
    ]:
        ok, details = _check_writable_directory(path)
        if ok:
            checks.add_row(label, "OK", details)
        else:
            checks.add_row(label, "FAIL", details)
            exit_code = 1

    for label, path in [
        ("Manifest file", settings.manifest.path),
        ("Queue state", settings.queue.state_path),
    ]:
        ok, details = _check_writable_file_parent(path)
        if ok:
            checks.add_row(label, "OK", details)
        else:
            checks.add_row(label, "FAIL", details)
            exit_code = 1

    pending_queue_items = len(QueueStateStore(settings.queue.state_path).load())
    checks.add_row("Queue status", "OK", f"{pending_queue_items} recoverable pending item(s)")

    try:
        ollama_client = OllamaClient(settings.ollama)
        if ollama_client.is_available():
            checks.add_row("Ollama", "OK", str(settings.ollama.host))
            if not hasattr(ollama_client, "model_exists"):
                checks.add_row("Ollama model", "WARN", "Model check unavailable")
            elif ollama_client.model_exists(settings.ollama.model):
                checks.add_row("Ollama model", "OK", settings.ollama.model)
            else:
                checks.add_row("Ollama model", "WARN", f"Model not listed: {settings.ollama.model}")
        else:
            checks.add_row("Ollama", "WARN", f"Could not reach {settings.ollama.host}")
            exit_code = max(exit_code, 1)
    except Exception as exc:
        checks.add_row("Ollama", "FAIL", str(exc))
        exit_code = 1

    console.print(checks)
    raise typer.Exit(exit_code)


@cli.command("config")
def config(environment: EnvironmentOption = None, as_json: ConfigJsonOption = False) -> None:
    """Show the resolved application configuration."""

    settings = _load_configured_settings(environment=environment)
    setup_logging(settings)
    logger.info("Configuration displayed")

    if as_json:
        console.print(RichJSON(settings.model_dump_json(indent=2)))
        return

    table = Table(title="Resolved Configuration", show_header=True, header_style="bold")
    table.add_column("Section")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("App", "Environment", settings.app.environment)
    table.add_row("Paths", "Project root", str(settings.paths.project_root))
    table.add_row("Paths", "Vault root", str(settings.paths.vault_root))
    table.add_row("Paths", "Log root", str(settings.paths.log_root))
    table.add_row("Watcher", "Enabled", str(settings.watcher.enabled))
    table.add_row("Watcher", "Inbox", str(settings.watcher.inbox_path))
    table.add_row("Watcher", "Processed", str(settings.watcher.processed_path))
    table.add_row("Watcher", "Failed", str(settings.watcher.failed_path))
    table.add_row("Watcher", "Recursive", str(settings.watcher.recursive))
    table.add_row("Watcher", "Interval", f"{settings.watcher.interval_seconds:g} second(s)")
    table.add_row("Watcher", "Extensions", ", ".join(settings.watcher.supported_extensions))
    table.add_row("Queue", "Enabled", str(settings.queue.enabled))
    table.add_row("Queue", "Workers", str(settings.queue.workers))
    table.add_row("Queue", "Maximum Size", str(settings.queue.max_size))
    table.add_row("Queue", "State", str(settings.queue.state_path))
    table.add_row("Manifest", "Enabled", str(settings.manifest.enabled))
    table.add_row("Manifest", "Path", str(settings.manifest.path))
    table.add_row("Manifest", "Entries", str(_manifest_count(settings)))
    table.add_row("Processing", "Move processed", str(settings.processing.move_processed))
    table.add_row("Processing", "Move failed", str(settings.processing.move_failed))
    table.add_row("Ollama", "Host", str(settings.ollama.host))
    table.add_row("Ollama", "Model", settings.ollama.model)
    table.add_row("Logging", "Level", settings.logging.level)
    console.print(table)


@cli.command("config-show", hidden=True)
def config_show() -> None:
    """Backward-compatible alias for the config command."""

    config(environment=None, as_json=False)


@cli.command("watch")
def watch() -> None:
    """Watch the inbox for new Markdown files."""

    settings = _load_configured_settings()
    setup_logging(settings)
    _ensure_runtime_directories(settings)

    inbox_display = _display_path(settings.watcher.inbox_path, settings.paths.project_root)
    table = Table(title="AI Memory Watcher", show_header=False, border_style="cyan")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Watching", inbox_display)
    table.add_row("Recursive", str(settings.watcher.recursive))
    table.add_row("Worker", _healthy("Running" if settings.queue.enabled else "Disabled"))
    table.add_row("Queue", _healthy("Ready"))
    table.add_row("Stop", "Press Ctrl+C to stop")
    console.print(table)

    service = WatchService(settings)
    service.run()


def main() -> None:
    """Run the CLI application."""

    cli()


def _run_ingest(source: str | Path, *, expected_source_type: str) -> None:
    settings = _load_configured_settings()
    setup_logging(settings)

    console.print(Panel.fit("Starting ingestion", title="Personal AI Memory"))

    try:
        ollama_client = OllamaClient(settings.ollama)
        workflow = IngestionWorkflow.from_runtime(
            ollama_client=ollama_client,
            writer=VaultWriter.from_settings(settings),
        )
        result = workflow.run(source, expected_source_type=expected_source_type)
    except (IngestionWorkflowError, AIProcessingError, OllamaClientError, OSError) as exc:
        logger.exception("Ingestion pipeline failed.")
        console.print(Panel(str(exc), title="Processing failed", border_style="red"))
        raise typer.Exit(1) from exc

    _print_ingest_success(
        source_type=result.document.source_type,
        note_title=result.note.title,
        note_path=result.write_result.note_path,
        created=result.write_result.created,
        updated=result.write_result.updated,
        attempts=result.ai_result.attempts,
    )


def _print_ingest_success(
    *,
    source_type: str,
    note_title: str,
    note_path: Path,
    created: bool,
    updated: bool,
    attempts: int,
) -> None:
    table = Table(title="Ingestion Complete", show_header=True, header_style="bold green")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Source type", source_type)
    table.add_row("Note", note_title)
    table.add_row("Path", str(note_path))
    table.add_row("Created", _yes_no(created))
    table.add_row("Updated", _yes_no(updated))
    table.add_row("AI attempts", str(attempts))
    console.print(table)


def _load_configured_settings(*, environment: str | None = None) -> Settings:
    try:
        return load_settings(environment=environment)
    except ConfigurationError as exc:
        console.print(Panel(str(exc), title="Configuration error", border_style="red"))
        raise typer.Exit(1) from exc


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _ensure_runtime_directories(settings: Settings) -> None:
    for path in [
        settings.watcher.inbox_path,
        settings.watcher.processed_path,
        settings.watcher.failed_path,
        settings.processing.processed_path,
        settings.processing.failed_path,
        settings.paths.log_root,
        settings.paths.cache_root,
        settings.paths.vault_root,
        settings.manifest.path.parent,
        settings.queue.state_path.parent,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def _manifest_count(settings: Settings) -> int:
    return ManifestManager(
        settings.manifest.path,
        project_root=settings.paths.project_root,
        enabled=settings.manifest.enabled,
    ).count()


def _ollama_status(settings: Settings) -> str:
    try:
        return "Connected" if OllamaClient(settings.ollama).is_available() else "Unavailable"
    except Exception:
        return "Unavailable"


def _is_writable_directory(path: Path) -> bool:
    ok, _details = _check_writable_directory(path)
    return ok


def _healthy(value: str) -> str:
    return f"[green]{value}[/green]"


def _status_style(value: str) -> str:
    if value in {"Connected", "Ready", "Configured", "Enabled"}:
        return f"[green]{value}[/green]"
    if value in {"Unavailable", "Not writable", "Disabled"}:
        return f"[yellow]{value}[/yellow]"
    return value


def _check_writable_directory(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".pam_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, str(path)
    except OSError as exc:
        return False, str(exc)


def _check_writable_file_parent(path: Path) -> tuple[bool, str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.parent / ".pam_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, str(path)
    except OSError as exc:
        return False, str(exc)


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)
