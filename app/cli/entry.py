"""CLI entrypoint for the Personal AI Memory System."""

from __future__ import annotations

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
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow, IngestionWorkflowError

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

    vault_root = settings.paths.vault_root
    notes_root = vault_root / "Notes"
    note_count = len(list(notes_root.glob("*.md"))) if notes_root.exists() else 0

    table = Table(title="Personal AI Memory Status", show_header=True, header_style="bold")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Environment", settings.app.environment)
    table.add_row("Vault", str(vault_root))
    table.add_row("Vault exists", _yes_no(vault_root.exists()))
    table.add_row("Generated notes", str(note_count))
    table.add_row("Ollama endpoint", str(settings.ollama.host))
    table.add_row("Ollama model", settings.ollama.model)
    table.add_row("Logs", str(settings.paths.log_root))

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

    for label, path in [
        ("Project root", settings.paths.project_root),
        ("Vault root", settings.paths.vault_root),
        ("Data inbox", settings.paths.inbox_root),
        ("Manifest root", settings.paths.manifest_root),
        ("Log root", settings.paths.log_root),
    ]:
        try:
            path.mkdir(parents=True, exist_ok=True)
            checks.add_row(label, "OK", str(path))
        except OSError as exc:
            checks.add_row(label, "FAIL", str(exc))
            exit_code = 1

    try:
        ollama_client = OllamaClient(settings.ollama)
        if ollama_client.is_available():
            checks.add_row("Ollama", "OK", str(settings.ollama.host))
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

    if as_json:
        console.print(RichJSON(settings.model_dump_json(indent=2)))
        return

    table = Table(title="Resolved Configuration", show_header=True, header_style="bold")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Environment", settings.app.environment)
    table.add_row("Project root", str(settings.paths.project_root))
    table.add_row("Vault root", str(settings.paths.vault_root))
    table.add_row("Inbox root", str(settings.paths.inbox_root))
    table.add_row("Manifest root", str(settings.paths.manifest_root))
    table.add_row("Log root", str(settings.paths.log_root))
    table.add_row("Ollama host", str(settings.ollama.host))
    table.add_row("Ollama model", settings.ollama.model)
    table.add_row("Logging level", settings.logging.level)
    console.print(table)


@cli.command("config-show", hidden=True)
def config_show() -> None:
    """Backward-compatible alias for the config command."""

    config(environment=None, as_json=False)


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
