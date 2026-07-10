"""Queue worker that routes files through the existing ingestion pipeline."""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Protocol

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from app.application import AIProcessingError
from app.core.config import Settings
from app.core.logging import get_logger
from app.infrastructure.llm import OllamaClient, OllamaClientError
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow, IngestionWorkflowError, IngestionWorkflowResult
from app.queue.manager import QueueManager
from app.queue.models import QueueItem, QueueStatus
from app.queue.state import QueueStateStore
from app.queue.stats import RuntimeStats

logger = get_logger(__name__)

SUPPORTED_PROCESSING_EXTENSIONS = {".md", ".txt", ".pdf"}


class ProcessingWorkflow(Protocol):
    """Protocol for the existing ingestion workflow boundary."""

    def run(
        self,
        source: str | Path,
        *,
        expected_source_type: str | None = None,
    ) -> IngestionWorkflowResult:
        """Run the existing document-to-vault workflow."""


class QueueWorker:
    """Process queued files one at a time."""

    def __init__(
        self,
        queue_manager: QueueManager,
        settings: Settings,
        manifest_manager: ManifestManager | None = None,
        workflow: ProcessingWorkflow | None = None,
        queue_state_store: QueueStateStore | None = None,
        stats: RuntimeStats | None = None,
        *,
        processing_seconds: float = 2.0,
        idle_sleep_seconds: float = 0.1,
    ) -> None:
        self.queue_manager = queue_manager
        self.settings = settings
        self.manifest_manager = manifest_manager or ManifestManager(
            settings.manifest.path,
            project_root=settings.paths.project_root,
            enabled=settings.manifest.enabled,
        )
        self.queue_state_store = queue_state_store
        self.stats = stats or RuntimeStats()
        self.processing_seconds = processing_seconds
        self.idle_sleep_seconds = idle_sleep_seconds
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._current_item_name: str | None = None
        self._workflow = workflow or self._build_workflow(settings)

    def start(self) -> None:
        """Start one background worker."""

        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = Thread(target=self.run_forever, name="queue-worker", daemon=True)
        self._thread.start()
        logger.info("Worker started")
        print("Worker started", flush=True)

    def stop(self, *, drain: bool = False) -> None:
        """Stop the background worker."""

        if drain:
            while self._current_item_name is not None or not self.queue_manager.is_empty():
                time.sleep(self.idle_sleep_seconds)

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
            logger.info("Worker stopped")
        self._save_queue_state()

    def run_forever(self) -> None:
        """Run until stopped, processing one queue item at a time."""

        while not self._stop_event.is_set():
            if not self.process_next():
                time.sleep(self.idle_sleep_seconds)

    def process_next(self) -> bool:
        """Process one item if available."""

        item = self.queue_manager.dequeue()
        if item is None:
            return False

        self._save_queue_state()
        self._current_item_name = item.path.name
        started = time.monotonic()
        queue_latency = max(0.0, (datetime.now(UTC) - item.created_at).total_seconds())
        logger.info("Queue processing started.", extra={"path": str(item.path)})
        try:
            return self._process_item(item, queue_latency=queue_latency, started=started)
        except Exception:
            logger.exception("Unexpected worker failure.", extra={"path": str(item.path)})
            self._fail_item(item)
            return True
        finally:
            self._current_item_name = None
            self.queue_manager.complete(item)
            self._save_queue_state()

    @property
    def is_processing(self) -> bool:
        return self._current_item_name is not None

    def _process_item(self, item: QueueItem, *, queue_latency: float, started: float) -> bool:
        source_type = self._source_type_for_extension(item.extension)
        if source_type is None:
            logger.warning("Unsupported file type queued.", extra={"path": str(item.path)})
            print("Unsupported file type", flush=True)
            self._fail_item(item)
            print("Done.", flush=True)
            print("Continue watching.", flush=True)
            return True

        with self._progress(item.path.name) as progress:
            task = progress.add_task(f"Processing {item.path.name}", total=6)
            self._advance(progress, task, "Reading document...")
            digest = self.manifest_manager.hash_for_path(item.path)
            logger.info("SHA256 calculated.", extra={"path": str(item.path), "sha256": digest})

            print("Duplicate check...", flush=True)
            print("Hash:", flush=True)
            print(digest, flush=True)
            if self.manifest_manager.contains_hash(digest):
                logger.info("Duplicate detected.", extra={"path": str(item.path), "sha256": digest})
                print("Duplicate?", flush=True)
                print("YES", flush=True)
                print("Skipping", flush=True)
                print(item.path.name, flush=True)
                item.status = QueueStatus.DONE
                self.stats.record_duplicate()
                return True

            print("Duplicate?", flush=True)
            print("No", flush=True)
            self._advance(progress, task, "Cleaning text...")
            logger.info(
                "Processing %s ingestion.",
                source_type.capitalize(),
                extra={"path": str(item.path)},
            )
            print(f"Processing {source_type.capitalize()}...", flush=True)
            print("Calling Ollama...", flush=True)
            self._advance(progress, task, "Sending to Ollama...")
            print("Generating note...", flush=True)
            self._advance(progress, task, "Generating knowledge...")
            print("Updating vault...", flush=True)

            try:
                result = self._workflow.run(item.path, expected_source_type=source_type)
            except (IngestionWorkflowError, AIProcessingError, OllamaClientError, OSError):
                logger.exception("File processing failed.", extra={"path": str(item.path)})
                print("Failed.", flush=True)
                self._fail_item(item)
                print("Continue watching.", flush=True)
                return True

            self._advance(progress, task, "Writing Markdown...")
            self.manifest_manager.add_processed_file(
                path=item.path,
                sha256=digest,
                extension=item.extension,
                generated_note=result.note.filename,
            )
            self.manifest_manager.save()
            logger.info("Manifest updated.", extra={"path": str(item.path), "sha256": digest})
            print("Manifest updated", flush=True)

            self._move_to_processed(item.path)
            self._advance(progress, task, "Finished")

        item.status = QueueStatus.DONE
        elapsed = time.monotonic() - started
        self.stats.record_processed(
            processing_seconds=elapsed,
            queue_latency_seconds=queue_latency,
        )
        print(f"Completed in {elapsed:.1f} seconds.", flush=True)
        print("Done.", flush=True)
        print("Continue watching.", flush=True)
        return True

    def _build_workflow(self, settings: Settings) -> ProcessingWorkflow:
        ollama_client = OllamaClient(settings.ollama)
        return IngestionWorkflow.from_runtime(
            ollama_client=ollama_client,
            writer=VaultWriter.from_settings(settings),
        )

    def _source_type_for_extension(self, extension: str) -> str | None:
        normalized = extension.lower()
        if normalized == ".md":
            return "markdown"
        if normalized == ".txt":
            return "text"
        if normalized == ".pdf":
            return "pdf"
        return None

    def _move_to_processed(self, source_path: Path) -> Path:
        destination_root = self.settings.processing.processed_path
        if not self.settings.processing.move_processed:
            return source_path

        return self._move_file(source_path, destination_root)

    def _fail_item(self, item: QueueItem) -> None:
        """Record a failed item without allowing cleanup failures to kill the worker."""

        try:
            self._move_to_failed(item.path)
        except OSError:
            logger.exception("Unable to move failed file.", extra={"path": str(item.path)})
        item.status = QueueStatus.FAILED
        self.stats.record_failed()

    def _move_to_failed(self, source_path: Path) -> Path:
        destination_root = self.settings.processing.failed_path
        if not self.settings.processing.move_failed:
            return source_path

        return self._move_file(source_path, destination_root)

    def _move_file(self, source_path: Path, destination_root: Path) -> Path:
        destination_root.mkdir(parents=True, exist_ok=True)
        destination = destination_root / source_path.name
        if destination.exists():
            destination = self._next_available_path(destination)

        shutil.move(str(source_path), str(destination))
        logger.info(
            "File moved.",
            extra={"source": str(source_path), "destination": str(destination)},
        )
        print("Moving file...", flush=True)
        print(str(destination), flush=True)
        return destination

    def _save_queue_state(self) -> None:
        if self.queue_state_store is not None:
            self.queue_state_store.save(self.queue_manager)

    def _progress(self, filename: str) -> Progress:
        return Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=Console(),
            transient=False,
        )

    @staticmethod
    def _advance(progress: Progress, task_id: TaskID, description: str) -> None:
        progress.update(task_id, description=description, advance=1)

    @staticmethod
    def _next_available_path(path: Path) -> Path:
        stem = path.stem
        suffix = path.suffix
        counter = 2
        while True:
            candidate = path.with_name(f"{stem} {counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1
