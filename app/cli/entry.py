"""CLI entrypoint for the Personal AI Memory System."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.json import JSON as RichJSON
from rich.panel import Panel
from rich.table import Table

from app.application import AIProcessingError, QAAnswer, QAError, QAWorkflow
from app.core.config import ConfigurationError, Settings, load_settings
from app.core.logging import get_logger, setup_logging
from app.domain.knowledge_graph import KnowledgeGraph
from app.infrastructure.llm import OllamaClient, OllamaClientError
from app.infrastructure.search import SearchHit, SearchService
from app.infrastructure.state.manifest import ManifestEntry, ManifestManager, is_successful_status
from app.infrastructure.vector_store import VectorStore
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
FilePathArgument = Annotated[
    Path,
    typer.Argument(
        help="Path to any supported file (auto-detected by content).",
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


@ingest_cli.command("file")
def ingest_file(path: FilePathArgument) -> None:
    """Ingest any supported file (auto-detected by content).

    This is the generic ingest entry point: type is auto-detected by the
    ingestion service, so the same command works for PDFs, Markdown, plain
    text, spreadsheets, images, audio, video, and more.
    """

    _run_ingest(path, expected_source_type=None)


@ingest_cli.command("pdf")
def ingest_pdf(path: PdfPathArgument) -> None:
    """Ingest a PDF file."""

    _run_ingest(path, expected_source_type=None)


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
    """Show a concise, truthful overview of current PAM state (read-only)."""

    settings = _load_configured_settings()
    setup_logging(settings)
    logger.info("Status requested")

    vault_root = settings.paths.vault_root
    notes_root = vault_root / "Notes"
    real_notes, placeholder_notes, other_notes = _note_counts(notes_root)

    ledger = _read_manifest_entries(settings)
    ledger_available = ledger is not None
    ledger = ledger if ledger is not None else []
    processed_count = sum(1 for entry in ledger if entry.get("status") == "processed")
    skipped_count = sum(
        1 for entry in ledger if entry.get("status") == "skipped_duplicate"
    )
    failed_count = sum(1 for entry in ledger if entry.get("status") == "failed")
    last_ingest = _last_ingestion(ledger)
    queue_waiting = _queue_waiting(settings)
    ollama_host = str(settings.ollama.host)
    indexed_chunks = _indexed_chunks(settings)
    indexed_sources = _indexed_sources(settings)
    vault_status = _vault_access_status(vault_root)

    table = Table(title="PAM Status (read-only)", show_header=True, header_style="bold")
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
    table.add_row("Items waiting", _status_style(queue_waiting), "Queue state file")
    table.add_row(
        "Manifest entries",
        _status_style(_ledger_metric(ledger_available, len(ledger))),
        "Durable ledger",
    )
    table.add_row("Sources indexed", _status_style(indexed_sources), "Vector store")
    table.add_row("Indexed chunks", _status_style(indexed_chunks), "Vector store")
    table.add_row(
        "Successful ingests",
        _status_style(_ledger_metric(ledger_available, processed_count)),
        "Durable ledger",
    )
    table.add_row(
        "Skipped duplicates",
        _status_style(_ledger_metric(ledger_available, skipped_count)),
        "Durable ledger",
    )
    table.add_row(
        "Failed",
        _status_style(_ledger_metric(ledger_available, failed_count)),
        "Durable ledger",
    )
    table.add_row(
        "Last ingestion",
        _status_style(_last_ingestion_display(last_ingest, ledger_available)),
        "",
    )
    table.add_row("Ollama host", _healthy("Configured"), ollama_host)
    table.add_row("Model", settings.ollama.model, "")
    table.add_row("Vault", _status_style(vault_status), str(vault_root))
    table.add_row("Real generated notes", _healthy(str(real_notes)), "")
    table.add_row("Placeholder notes", _status_style(_placeholder_style(placeholder_notes)), "")
    if other_notes:
        table.add_row("User/other notes", str(other_notes), "")
    table.add_row("Logs", _healthy("Ready"), str(settings.paths.log_root))
    console.print(table)


@dataclass(slots=True)
class SourceRow:
    """A single indexed source with its metadata for ``pam sources``.

    ``manifest_matches`` records the ledger entries attributed to the source
    so the presentation (status / last ingested) stays derived from durable
    state without inventing fields.
    """

    source: str
    type: str
    chunks: int = 0
    status: str = "indexed"
    last_ingested: str | None = None
    manifest_matches: list[ManifestEntry] = field(default_factory=list)


@cli.command("sources")
def sources() -> None:
    """List the sources currently indexed by PAM (read-only).

    The persistent vector store is the authority on what is indexable; the
    durable ledger (manifest) annotates each with ingestion status and the most
    recent successful ingestion time.  This command never queries the corpus,
    launches an LLM, or performs retrieval — it only reads durable state.
    """

    settings = _load_configured_settings()
    setup_logging(settings)
    logger.info("Sources requested")

    rows = _read_vector_store_sources(settings)
    if rows is None:
        console.print(
            Panel.fit(
                "The vector store could not be read; source listing is unavailable.",
                title="Sources unavailable",
                border_style="red",
            ),
        )
        raise typer.Exit(1)

    if not rows:
        console.print(
            Panel.fit(
                "No sources are indexed yet. Run `pam ingest file <path>` to add one.",
                title="Sources",
            ),
        )
        return

    manifest = ManifestManager(
        settings.manifest.path,
        project_root=settings.paths.project_root,
        enabled=settings.manifest.enabled,
    )
    _annotate_source_ledger(rows, manifest, settings.paths.project_root)

    table = Table(title="Indexed Sources", show_header=True, header_style="bold")
    table.add_column("Source")
    table.add_column("Type")
    table.add_column("Chunks", justify="right")
    table.add_column("Status")
    table.add_column("Last Ingested (UTC)")

    for row in rows:
        table.add_row(
            row.source,
            row.type if row.type else "—",
            str(row.chunks),
            _source_status_style(row.status),
            row.last_ingested if row.last_ingested else "—",
        )

    console.print(table)
    logger.info(
        "Sources listed.",
        extra={"source_count": len(rows), "chunk_count": sum(r.chunks for r in rows)},
    )


def _read_vector_store_sources(settings: Settings) -> list[SourceRow] | None:
    """Return per-source rows from the persistent vector store, or ``None``.

    ``None`` signals the store cannot be read (no fabricated zero).  Rows are
    grouped by the canonical ``source`` value and sorted deterministically by
    source string.  ``type`` is the first observed ``source_type``.
    """
    store_path = settings.paths.manifest_root / "vector_store.json"
    if not store_path.exists():
        return []

    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
        entries = data.get("entries", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(entries, list):
        return None

    by_source: dict[str, SourceRow] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source", ""))
        if not source:
            continue
        row = by_source.get(source)
        if row is None:
            by_source[source] = SourceRow(
                source=source,
                type=str(entry.get("source_type", "") or ""),
            )
            row = by_source[source]
        row.chunks += 1
        if not row.type and entry.get("source_type"):
            row.type = str(entry["source_type"])

    return [by_source[source] for source in sorted(by_source)]


def _annotate_source_ledger(
    rows: list[SourceRow],
    manifest: ManifestManager,
    project_root: Path,
) -> None:
    """Annotate each source row with ledger status and last successful ingest."""
    entries = manifest.list_entries()
    for row in rows:
        targets = _source_forms(row.source, project_root)
        matched = [
            entry
            for entry in entries
            if _manifest_entry_matches(
                entry.original_path,
                entry.original_filename,
                entry.sha256,
                targets,
            )
        ]
        row.manifest_matches = matched

        status = "indexed"
        last_ingested: str | None = None
        for entry in matched:
            if entry.status == "failed":
                status = "failed"
            elif status == "indexed" and entry.status in {"processed", "skipped_duplicate"}:
                status = entry.status
            if is_successful_status(entry.status) and (
                last_ingested is None or entry.processed_at > last_ingested
            ):
                last_ingested = entry.processed_at
        row.status = status
        row.last_ingested = last_ingested


def _source_status_style(status: str) -> str:
    """Return a status string styled consistently with ``status`` output."""
    if status == "indexed":
        return "indexed (no ledger)"
    return status


@cli.command("remove")
def remove_source(
    source: Annotated[str, typer.Argument(help="Source path or URL to remove.")],
) -> None:
    """Remove one source from the index (vectors, KG, and ledger).

    Identifies the source deterministically, removes only its vector chunks,
    knowledge-graph nodes/edges, and manifest entries. Never deletes vault
    notes (which may hold user-written content) and provides no 'remove
    everything' operation. BM25 state is rebuilt automatically on next use.
    Unknown sources and ambiguous matches abort without deleting anything.
    """
    settings = _load_configured_settings()
    setup_logging(settings)
    project_root = settings.paths.project_root
    targets = _source_forms(source, project_root)

    store = VectorStore(
        persistence_path=settings.paths.manifest_root / "vector_store.json",
    )

    graph_path = settings.paths.manifest_root / "knowledge_graph.json"
    if graph_path.exists():
        try:
            kg = KnowledgeGraph.load(graph_path)
        except (OSError, ValueError) as exc:
            console.print(
                Panel.fit(
                    "Could not read the knowledge graph; nothing was removed.",
                    border_style="red",
                    title="Remove failed",
                ),
            )
            logger.error("Knowledge graph read failed during remove: %s", exc)
            raise typer.Exit(1) from exc
    else:
        kg = KnowledgeGraph()

    manifest = ManifestManager(
        settings.manifest.path,
        project_root=project_root,
        enabled=settings.manifest.enabled,
    )
    ledger_matches = [
        entry
        for entry in manifest.list_entries()
        if _manifest_entry_matches(
            entry.original_path,
            entry.original_filename,
            entry.sha256,
            targets,
        )
    ]

    matched = {
        _canonical_source(entry.source, project_root)
        for entry in store.entries()
        if entry.source in targets
    }
    matched |= {
        _canonical_source(node.source, project_root)
        for node in kg.nodes.values()
        if node.source in targets
    }
    matched |= {
        _canonical_source(entry.original_path, project_root)
        for entry in ledger_matches
    }

    if len(matched) > 1:
        console.print(
            Panel.fit(
                f"'{source}' matches multiple sources. Use an absolute path or "
                "a more specific source so only the intended one is removed.",
                border_style="red",
                title="Remove aborted (ambiguous source)",
            ),
        )
        raise typer.Exit(1)
    if not matched:
        console.print(
            Panel.fit(
                f"No indexed source matching '{source}'.",
                border_style="red",
                title="Source not found",
            ),
        )
        raise typer.Exit(1)

    # Resolve basename/normalized matches to the full ownership key so the
    # vector and graph stores (keyed by absolute path / verbatim URL) agree
    # with the ledger identity.
    resolved = set(targets)
    for canonical in matched:
        res = Path(canonical)
        if not res.is_absolute():
            resolved.add(str((project_root / res).resolve()))
    targets = resolved

    removed_chunks = 0
    for target in targets:
        removed_chunks += store.remove_by_source(target)
    store.save()

    removed_nodes = 0
    removed_edges = 0
    for target in targets:
        nodes, edges = kg.remove_source(target)
        removed_nodes += nodes
        removed_edges += edges
    kg.save(graph_path)

    removed_ledger = 0
    for entry in ledger_matches:
        entry_path = Path(entry.original_path)
        if not entry_path.is_absolute():
            entry_path = project_root / entry_path
        if manifest.remove_entry(path=entry_path):
            removed_ledger += 1
    manifest.save()

    table = Table(title="Source Removed", show_header=True, header_style="bold")
    table.add_column("Item")
    table.add_column("Count")
    table.add_row("Source", source)
    table.add_row("Vector chunks removed", str(removed_chunks))
    table.add_row("KG nodes removed", str(removed_nodes))
    table.add_row("KG edges removed", str(removed_edges))
    table.add_row("Ledger entries removed", str(removed_ledger))
    console.print(table)
    logger.info(
        "Removed source from index.",
        extra={
            "source": source,
            "chunks": removed_chunks,
            "nodes": removed_nodes,
            "edges": removed_edges,
            "ledger": removed_ledger,
        },
    )

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

    ollama_available = False
    try:
        ollama_client = OllamaClient(settings.ollama)
        if ollama_client.is_available():
            ollama_available = True
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

    ocr_cfg = settings.intelligence.ocr
    checks.add_row(
        "OCR",
        "Enabled" if ocr_cfg.enabled else "Disabled",
        f"engine={ocr_cfg.engine}, page_limit={ocr_cfg.page_limit or 'all'}",
    )
    checks.add_row(
        "Vision model",
        "OK" if ollama_available else "WARN",
        f"{settings.models.vision}" + ("" if ollama_available else " (Ollama unreachable)"),
    )
    tesseract_binary = (
        ocr_cfg.tesseract_cmd
        if ocr_cfg.tesseract_cmd and Path(ocr_cfg.tesseract_cmd).exists()
        else (shutil.which("tesseract") or "")
    )
    checks.add_row(
        "Tesseract binary",
        "OK" if tesseract_binary else "WARN",
        tesseract_binary or "not on PATH (set intelligence.ocr.tesseract_cmd)",
    )
    checks.add_row(
        "pytesseract",
        "OK" if find_spec("pytesseract") else "WARN",
        "Installed" if find_spec("pytesseract") else "Not installed (pip install pytesseract)",
    )
    checks.add_row(
        "Preprocessing (Pillow)",
        "OK" if find_spec("PIL") else "WARN",
        "Installed" if find_spec("PIL") else "Not installed",
    )

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


@cli.command("search")
def search(
    query: Annotated[str, typer.Argument(help="Search query text.")],
    top_k: Annotated[
        int,
        typer.Option("--top-k", min=1, help="Number of results to return."),
    ] = 5,
    source_type: Annotated[
        str | None,
        typer.Option(
            "--source-type",
            help="Only show results of this source type (e.g. pdf, markdown).",
        ),
    ] = None,
    min_score: Annotated[
        float,
        typer.Option("--min-score", help="Minimum retrieval score."),
    ] = 0.0,
    filter_json: Annotated[
        str | None,
        typer.Option("--filter", help="JSON object of exact-match metadata filters."),
    ] = None,
) -> None:
    """Search the knowledge base and show ranked results."""

    settings = _load_configured_settings()
    setup_logging(settings)

    query = query.strip()
    if not query:
        console.print(
            Panel("Search query must not be empty.", title="Search", border_style="red"),
        )
        raise typer.Exit(1)

    filters = _parse_search_filters(filter_json, source_type)
    if filters is None:
        raise typer.Exit(1)

    try:
        service = SearchService.create_default(settings)
        hits = service.search(
            query, top_k=top_k, filter=filters or None, min_score=min_score,
        )
    except Exception as exc:
        logger.exception("Search failed.")
        console.print(Panel(str(exc), title="Search failed", border_style="red"))
        raise typer.Exit(1) from exc

    _print_search_results(query, hits)


@cli.command("ask")
def ask(
    question: Annotated[str, typer.Argument(help="Question to answer.")],
    top_k: Annotated[
        int,
        typer.Option("--top-k", min=1, help="Number of retrieved context sources."),
    ] = 5,
    min_score: Annotated[
        float,
        typer.Option("--min-score", help="Minimum retrieval score."),
    ] = 0.0,
    filter_json: Annotated[
        str | None,
        typer.Option("--filter", help="JSON object of exact-match metadata filters."),
    ] = None,
) -> None:
    """Answer a question grounded in the knowledge base (RAG)."""

    settings = _load_configured_settings()
    setup_logging(settings)

    question = question.strip()
    if not question:
        console.print(
            Panel("Question must not be empty.", title="Ask", border_style="red"),
        )
        raise typer.Exit(1)

    filters = _parse_search_filters(filter_json, None)
    if filters is None:
        raise typer.Exit(1)

    try:
        workflow = QAWorkflow.create_default(settings)
        result = workflow.ask(
            question, top_k=top_k, min_score=min_score, filter=filters or None,
        )
    except QAError as exc:
        logger.exception("Question answering failed.")
        console.print(Panel(str(exc), title="Ask failed", border_style="red"))
        raise typer.Exit(1) from exc
    except Exception as exc:
        logger.exception("Question answering failed.")
        console.print(Panel(str(exc), title="Ask failed", border_style="red"))
        raise typer.Exit(1) from exc

    _print_qa_answer(question, result)


def main() -> None:
    """Run the CLI application."""

    cli()


def _parse_search_filters(
    filter_json: str | None,
    source_type: str | None,
) -> dict[str, object] | None:
    """Parse --filter JSON and merge --source-type; None signals a usage error."""
    filters: dict[str, object] = {}
    if filter_json:
        try:
            parsed = json.loads(filter_json)
        except json.JSONDecodeError as exc:
            console.print(
                Panel(f"Invalid --filter JSON: {exc}", title="Search", border_style="red"),
            )
            return None
        if not isinstance(parsed, dict):
            console.print(
                Panel("--filter must be a JSON object.", title="Search", border_style="red"),
            )
            return None
        filters.update(parsed)
    if source_type:
        filters["source_type"] = source_type
    return filters


def _print_search_results(query: str, hits: list[SearchHit]) -> None:
    if not hits:
        console.print("No results found.")
        return
    table = Table(title=f"Search: {query}", show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Source")
    table.add_column("Type")
    table.add_column("Snippet", overflow="fold")
    for hit in hits:
        table.add_row(
            f"{hit.score:.4f}",
            hit.source,
            hit.source_type,
            " ".join(hit.text.split())[:200],
        )
    console.print(table)


def _print_qa_answer(question: str, result: QAAnswer) -> None:
    outcome = getattr(result, "outcome", "answered")
    origin = getattr(result, "origin", "retrieval")

    if origin == "system":
        console.print(
            Panel(result.answer, title="System facts",
                  border_style="cyan"),
        )
        console.print(
            "[cyan]Answer from PAM runtime/configuration "
            "(no retrieval, no LLM, no vector search).[/cyan]"
        )
        return

    if outcome == "abstained":
        console.print(
            Panel(result.answer, title="Insufficient evidence", border_style="yellow"),
        )
        reason = getattr(result, "abstention_reason", None)
        if reason:
            console.print(f"[yellow]Abstention reason: {reason}[/yellow]")
        return

    console.print(Panel(result.answer, title=f"Answer: {question}", border_style="green"))

    citations = getattr(result, "citations", None)
    invalid = getattr(result, "invalid_citations", None)
    duplicates = getattr(result, "duplicate_citations", 0)

    if citations:
        console.print("[green]ANSWERED — SOURCES VERIFIED[/green]")
        table = Table(title="Sources", show_header=True, header_style="bold")
        table.add_column("#", justify="right")
        table.add_column("Document")
        table.add_column("Section")
        table.add_column("Type")
        table.add_column("Score", justify="right")
        table.add_column("Snippet", overflow="fold")
        for citation in citations:
            hit = citation.hit
            section = (
                hit.metadata.get("heading") if hit.metadata else None
            ) or (
                hit.metadata.get("parent_heading") if hit.metadata else None
            ) or "—"
            table.add_row(
                str(citation.number),
                Path(hit.source).name or hit.source,
                str(section),
                hit.source_type or "—",
                f"{hit.score:.4f}",
                " ".join(hit.text.split())[:200],
            )
        console.print(table)
    elif result.sources:
        console.print("[yellow]ANSWERED — NO CITATIONS PROVIDED[/yellow]")
        table = Table(title="Sources", show_header=True, header_style="bold")
        table.add_column("Score", justify="right")
        table.add_column("Source")
        table.add_column("Snippet", overflow="fold")
        for hit in result.sources:
            table.add_row(
                f"{hit.score:.4f}",
                hit.source,
                " ".join(hit.text.split())[:200],
            )
        console.print(table)
    else:
        console.print("No sources retrieved.")

    if duplicates:
        console.print(
            f"[yellow]Note: {duplicates} repeated citation(s) were deduplicated.[/yellow]"
        )
    if invalid:
        numbers = ", ".join(f"[SOURCE {n}]" for n in invalid)
        console.print(
            Panel(
                f"Answer cited {numbers}, which is not among the retrieved "
                "sources. No fabricated source was created and no citation "
                "was renumbered.",
                title="Invalid citations",
                border_style="yellow",
            ),
        )


def _run_ingest(source: str | Path, *, expected_source_type: str | None) -> None:
    settings = _load_configured_settings()
    setup_logging(settings)

    console.print(Panel.fit("Starting ingestion", title="Personal AI Memory"))

    # The processed-files manifest doubles as the durable ingestion ledger
    # (Phase 6A): every attempt records processed / skipped_duplicate / failed.
    manifest = ManifestManager(
        settings.manifest.path,
        project_root=settings.paths.project_root,
        enabled=settings.manifest.enabled,
    )
    ledger_path = Path(source)
    try:
        digest = manifest.hash_for_path(source) if isinstance(source, Path) else None
    except ValueError:
        # Unsupported/undigestible file type: let the workflow decide and
        # present the truthful outcome rather than leaking a raw hash error.
        digest = None

    if digest is not None and manifest.contains_successful_hash(digest):
        manifest.add_processed_file(
            path=ledger_path,
            sha256=digest,
            extension=ledger_path.suffix,
            status="skipped_duplicate",
        )
        _try_save_ledger(manifest)
        console.print(
            Panel.fit(
                "This file was already processed successfully (identical content); "
                "skipping. Existing note, index, and knowledge-graph data for this "
                "source was left untouched.",
                title="Ingest skipped (duplicate)",
            ),
        )
        return
    if digest is None and manifest.contains_path(ledger_path):
        manifest.add_processed_file(
            path=ledger_path,
            sha256="",
            extension=ledger_path.suffix,
            status="skipped_duplicate",
        )
        _try_save_ledger(manifest)
        console.print(
            Panel.fit(
                "This source was already recorded; skipping. Existing note, index, "
                "and knowledge-graph data for this source was left untouched.",
                title="Ingest skipped (duplicate)",
            ),
        )
        return

    try:
        workflow = IngestionWorkflow.create_default(settings)
        result = workflow.run(source, expected_source_type=expected_source_type)
    except (IngestionWorkflowError, AIProcessingError, OllamaClientError, OSError) as exc:
        logger.error("Ingestion pipeline failed: %s", exc)
        _record_failed_ingest(manifest, ledger_path, digest, exc)
        _print_ingest_failure(
            category=getattr(exc, "category", "retryable"),
            reason=str(exc),
        )
        raise typer.Exit(1) from exc
    except Exception as exc:
        logger.error("Unexpected failure during ingestion: %s", exc)
        _record_failed_ingest(manifest, ledger_path, digest, exc)
        _print_ingest_failure(
            category="retryable",
            reason=str(exc) or exc.__class__.__name__,
        )
        raise typer.Exit(1) from exc

    embedded = getattr(result, "embedding_succeeded", True)
    indexed = getattr(result, "indexing_succeeded", True)
    fully_indexed = embedded and indexed
    manifest.add_processed_file(
        path=ledger_path,
        sha256=digest or "",
        extension=ledger_path.suffix,
        generated_note=result.note.filename,
        chunks_stored=getattr(result, "chunks_stored", False),
        embedding_succeeded=embedded,
        indexing_succeeded=indexed,
        status="processed" if fully_indexed else "failed",
        error_reason=(
            None
            if fully_indexed
            else getattr(result, "engine_error", None) or "unknown engine failure"
        ),
    )
    _try_save_ledger(manifest)

    if not fully_indexed:
        reason = getattr(result, "engine_error", None) or "unknown engine failure"
        console.print(
            Panel.fit(
                f"The note was written, but the source was not fully indexed "
                f"({reason}). The ledger records this attempt as failed; you can "
                f"retry ingestion to complete the index.",
                title="Ingestion incomplete",
                border_style="red",
            ),
        )
        raise typer.Exit(1)

    if not getattr(result, "graph_succeeded", True) and getattr(
        result, "chunks_stored", False
    ):
        console.print(
            Panel.fit(
                "The note and chunks were indexed, but the knowledge graph could "
                "not be updated for this source. Everything else was saved.",
                title="Knowledge graph warning",
                border_style="yellow",
            ),
        )

    _print_ingest_success(
        source=getattr(result.document, "source", ledger_path),
        source_type=result.document.source_type,
        note_title=result.note.title,
        note_path=result.write_result.note_path,
        created=result.write_result.created,
        updated=result.write_result.updated,
        attempts=result.ai_result.attempts,
        chunks_stored=getattr(result, "chunks_stored", False),
        indexed=fully_indexed,
    )


def _record_failed_ingest(
    manifest: ManifestManager,
    path: Path,
    digest: str | None,
    exc: Exception,
) -> None:
    """Record a failed ingest attempt in the durable ledger."""
    manifest.add_failed_file(
        path=path,
        sha256=digest or "",
        extension=path.suffix,
        error_reason=f"{exc.__class__.__name__}: {exc}",
    )
    _try_save_ledger(manifest)


def _try_save_ledger(manifest: ManifestManager) -> None:
    """Persist the ledger, tolerating a disk failure."""
    try:
        manifest.save()
    except OSError:
        logger.exception("Ledger save failed; keeping in-memory record.")


def _print_ingest_success(
    *,
    source: str | Path,
    source_type: str,
    note_title: str,
    note_path: Path,
    created: bool,
    updated: bool,
    attempts: int,
    chunks_stored: int = 0,
    indexed: bool = True,
) -> None:
    table = Table(title="Ingestion Complete", show_header=True, header_style="bold green")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Source", str(source))
    table.add_row("Source type", source_type)
    table.add_row("Note", note_title)
    table.add_row("Path", str(note_path))
    table.add_row("Created", _yes_no(created))
    table.add_row("Updated", _yes_no(updated))
    table.add_row("AI attempts", str(attempts))
    table.add_row("Chunks indexed", str(chunks_stored))
    table.add_row("Indexed", _yes_no(indexed))
    console.print(table)


def _print_ingest_failure(*, category: str, reason: str) -> None:
    """Present a failed ingest with the truthful outcome category."""
    if category == "blocked":
        console.print(
            Panel.fit(
                f"{reason} The file was not read and no contents were indexed.",
                title="Ingest blocked (security)",
                border_style="red",
            ),
        )
        return
    if category == "unsupported":
        console.print(
            Panel.fit(
                f"{reason} Ingest a supported file type and try again.",
                title="Unsupported source",
                border_style="yellow",
            ),
        )
        return
    console.print(
        Panel.fit(
            f"{reason} You can retry after resolving the underlying issue "
            f"(e.g. Ollama offline, model unavailable, or transient error).",
            title="Processing failed",
            border_style="red",
        ),
    )


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


def _read_manifest_entries(settings: Settings) -> list[dict] | None:
    """Return the durable ledger entries read-only, or ``None`` if unreadable.

    Unlike ``ManifestManager`` construction, this never creates directories,
    writes a fresh manifest, or quarantines a recreated file: status must not
    mutate durable state. A missing manifest is a genuinely empty ledger (``[]``);
    a present-but-unreadable one is ``None``, never a fabricated zero.
    """
    manifest_path = settings.manifest.path
    if not manifest_path.is_absolute():
        manifest_path = settings.paths.project_root / manifest_path
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    files = data.get("files", []) if isinstance(data, dict) else []
    if not isinstance(files, list):
        return None
    return [entry for entry in files if isinstance(entry, dict)]


def _ledger_metric(available: bool, value: int) -> str:
    """Render a ledger-derived count, preserving unavailable state."""
    return str(value) if available else "unavailable"


def _last_ingestion(entries: list[dict]) -> str | None:
    """Return the most recent successful ingestion timestamp, if any.

    Derived purely from durable ledger ``processed_at`` values; never the
    process start time, the clock, or filesystem mtimes.
    """
    latest: str | None = None
    for entry in entries:
        if entry.get("status") not in {"processed", "skipped_duplicate"}:
            continue
        processed_at = entry.get("processed_at")
        if not isinstance(processed_at, str) or not processed_at:
            continue
        if latest is None or processed_at > latest:
            latest = processed_at
    return latest


def _last_ingestion_display(last_ingest: str | None, ledger_available: bool) -> str:
    """Present last-ingestion truthfully: value, ``never``, or ``unavailable``."""
    if not ledger_available:
        return "unavailable"
    return last_ingest if last_ingest else "never"


def _queue_waiting(settings: Settings) -> str:
    """Return the pending queue item count, or ``unavailable`` when unreadable.

    ``QueueStateStore.load`` swallows unreadable state into an empty list so the
    worker's restart path can recover; status must not report a fabricated zero,
    so readability of the state file is verified first.
    """
    path = settings.queue.state_path
    if not path.exists():
        return "0"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError, ValueError):
        return "unavailable"
    if not isinstance(items, list):
        return "unavailable"
    return str(len(QueueStateStore(path).load()))


def _vault_access_status(path: Path) -> str:
    """Read-only vault availability check (never writes a probe file)."""
    if not path.exists():
        return "Missing"
    try:
        return "Connected" if os.access(path, os.W_OK) else "Not writable"
    except OSError:
        return "Unavailable"


def _indexed_chunks(settings: Settings) -> str:
    """Return the number of entries in the persisted vector store.

    Reports ``unavailable`` when the store cannot be read, rather than
    fabricating a zero.  The store is written as ``{"entries": [...]}`` by
    ``VectorStore.save``; reading it here is presentation-only and never
    modifies retrieval state.
    """
    store_path = settings.paths.manifest_root / "vector_store.json"
    if not store_path.exists():
        return "0"
    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
        entries = data.get("entries", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError):
        return "unavailable"
    return str(len(entries)) if isinstance(entries, list) else "unavailable"


def _indexed_sources(settings: Settings) -> str:
    """Return the number of distinct sources in the persisted vector store."""
    store_path = settings.paths.manifest_root / "vector_store.json"
    if not store_path.exists():
        return "0"
    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
        entries = data.get("entries", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError):
        return "unavailable"
    if not isinstance(entries, list):
        return "unavailable"
    return str(len({entry.get("source", "") for entry in entries if isinstance(entry, dict)}))


def _note_counts(notes_root: Path) -> tuple[int, int, int]:
    """Classify vault notes into (real generated, placeholder, user/other).

    Placeholder stubs are auto-created notes with ``source_type: placeholder``
    (see ``WikiManager.create_placeholder``) and must not be reported as real
    notes.  Real generated notes carry a ``source`` frontmatter; anything else
    is a user/other note.
    """
    real = placeholder = other = 0
    if not notes_root.exists():
        return 0, 0, 0
    for path in notes_root.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            other += 1
            continue
        source_type = _frontmatter_value(text, "source_type")
        has_source = _frontmatter_value(text, "source") is not None
        if source_type == "placeholder":
            placeholder += 1
        elif has_source:
            real += 1
        else:
            other += 1
    return real, placeholder, other


def _placeholder_style(count: int) -> str:
    return f"[yellow]{count}[/yellow]" if count else str(count)


def _frontmatter_value(text: str, key: str) -> str | None:
    match = re.match(r"\A---\n(?P<frontmatter>.*?)\n---\n?", text, re.DOTALL)
    if match is None:
        return None
    pattern = re.compile(
        rf"^{re.escape(key)}:\s*[\"']?(?P<value>.+?)[\"']?\s*$", re.MULTILINE
    )
    value_match = pattern.search(match.group("frontmatter"))
    if value_match is None:
        return None
    return value_match.group("value").strip()


def _healthy(value: str) -> str:
    return f"[green]{value}[/green]"


def _status_style(value: str) -> str:
    if value in {"Connected", "Ready", "Configured", "Enabled"}:
        return f"[green]{value}[/green]"
    if value in {"Unavailable", "Not writable", "Disabled", "Missing"}:
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


def _source_forms(source: str, project_root: Path) -> set[str]:
    """Candidate source identifiers for a delete target.

    Ingestion canonicalizes ``document.source`` to the absolute resolved path
    for files and keeps the URL string verbatim for remote sources.  The
    manifest records the project-relative path.  Returning all forms lets a
    single ``pam remove`` argument (absolute path, relative path, or URL)
    deterministically match every subsystem's ownership key.
    """
    forms = {source}
    if "://" in source:
        # Ledger rows for URL sources are keyed by a Path-mangled form of the
        # URL; include those resolved/relative forms alongside the verbatim
        # value so the ledger and the vector/graph stores both match.
        try:
            converted = Path(source)
            resolved = converted.resolve()
            forms.add(str(converted))
            forms.add(str(resolved))
            with suppress(ValueError):
                forms.add(str(resolved.relative_to(project_root)))
        except OSError:
            pass
        return forms
    path = Path(source).expanduser()
    try:
        if path.is_absolute():
            resolved = path.resolve()
        else:
            # Resolve relative inputs against the project root rather than the
            # CWD so ``pam remove notes/a.md`` works from any directory.
            resolved = (project_root / source).resolve()
    except OSError:
        return forms
    forms.add(str(resolved))
    with suppress(ValueError):
        forms.add(str(resolved.relative_to(project_root)))
    with suppress(ValueError):
        forms.add(str(path.relative_to(project_root)))
    return forms


def _canonical_source(value: str, project_root: Path) -> str:
    """Unify a vector/KG/ledger identity into one comparable key.

    Mirrors the manifest's own normalization (resolve, then project-relative
    when possible) so a single source compares equal across the vector store,
    knowledge graph, and ledger regardless of absolute/relative/URL spelling.
    """
    p = Path(value)
    if not p.is_absolute():
        p = project_root / p
    try:
        return str(p.resolve().relative_to(project_root))
    except ValueError:
        return str(p.resolve())


def _manifest_entry_matches(
    original_path: str,
    original_filename: str,
    sha256: str,
    targets: set[str],
) -> bool:
    """Return whether a manifest entry belongs to a delete target."""
    if not sha256 and not original_path and not original_filename:
        return False
    if original_path in targets:
        return True
    if original_filename in targets:
        return True
    try:
        if str(Path(original_path).resolve()) in targets:
            return True
    except OSError:
        pass
    return Path(original_filename).name in targets

