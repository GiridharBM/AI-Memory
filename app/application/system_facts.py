"""Deterministic System Facts layer (Phase 6I-B).

Answers known PAM / system-meta questions from authoritative application state
and configuration WITHOUT invoking retrieval, the LLM, or the network.

This layer removes the known F-class ("ask about the tool") category from the
normal retrieval path.  It is NOT a general evidence verifier and does not
attempt to solve the overall false-positive-rate problem.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.infrastructure.state.manifest import ManifestManager

logger = get_logger(__name__)

VECTOR_STORE_FILENAME = "vector_store.json"

# Stable, human-readable ingestion capabilities.  Derived from the canonical
# routing kinds in app/infrastructure/routing/processors.py (frozen at V1).
SUPPORTED_INGESTION_TYPES = (
    "PDF (text + scanned/OCR), Word (.docx), PowerPoint (.pptx), Markdown, "
    "plain text, EPUB, TeX; CSV, Excel (.xlsx), notebooks, databases; "
    "source code & config files; images (with OCR), audio, video, diagrams; "
    "HTML/JSON/XML, email, archives, GitHub README, YouTube transcripts"
)

# Ollama context length validated during Phase 6F (runtime setting, not in
# config/default.yaml).
OLLAMA_NUM_CTX = 8192


class Intent(str):
    """Supported system-facts intents."""

    VERSION = "version"
    SOURCE_COUNT = "source_count"
    CHUNK_COUNT = "chunk_count"
    FEATURE_STATUS = "feature_status"
    QA_MODEL = "qa_model"
    CAPABILITIES = "capabilities"
    STATUS = "status"


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip().lower())


@dataclass(slots=True)
class SystemFact:
    """A single deterministic system fact."""

    intent: Intent
    label: str
    value: str
    detail: str = ""

    @property
    def answer(self) -> str:
        return f"{self.value} ({self.detail})" if self.detail else self.value


class SystemFactsRouter:
    """Deterministic, conservative router for system-facts queries.

    Uses explicit phrase/substring matching.  It intentionally does NOT use an
    LLM and requires a specific signal for each intent so it never hijacks
    normal knowledge questions ("What is PAM?", "What did I learn about
    Docker?" are left to normal QA).
    """

    _VERSION_RE = re.compile(r"\b(what|which)\s+version\b")
    _HOW_MANY_RE = re.compile(r"\bhow many\b")
    _WORD_RE = r"\b{word}\b"

    def __init__(self) -> None:
        self._feature_terms = ("reranker", "hyde", "answerability", "feature", "flag")

    def route(self, question: str) -> Intent | None:
        q = _normalize(question)
        if not q:
            return None
        checkers = (
            (Intent.VERSION, self._match_version),
            (Intent.FEATURE_STATUS, self._match_feature),
            (Intent.QA_MODEL, self._match_qa_model),
            (Intent.CAPABILITIES, self._match_capabilities),
            (Intent.SOURCE_COUNT, self._match_source_count),
            (Intent.CHUNK_COUNT, self._match_chunk_count),
            (Intent.STATUS, self._match_status),
        )
        for intent, fn in checkers:
            if fn(q):
                return intent
        return None

    def _match_version(self, q: str) -> bool:
        if "version" not in q:
            return False
        if self._VERSION_RE.search(q):
            # "what version ... running?" is a system-facts query; "what
            # version of X supports Y" (a knowledge question) does not mention
            # the running PAM instance and stays with normal QA.
            return any(
                t in q
                for t in ("running", "pam", "app", "system", "installed", "current", "you on")
            )
        return ("pam version" in q) or ("version of pam" in q)

    def _match_feature(self, q: str) -> bool:
        if not any(t in q for t in self._feature_terms):
            return False
        return any(s in q for s in ("enabled", "disabled", "on", "off", "active", "turned"))

    def _match_qa_model(self, q: str) -> bool:
        if "model" not in q:
            return False
        if any(
            t in q
            for t in (
                "what model", "which model", "model answers", "model do you", "model are you",
            )
        ):
            return True
        # "what QA model is PAM using?" reads as "qa model", not "what model".
        # Gate on a self/tool signal so generic knowledge questions about
        # "QA model" (e.g. "What is QA model evaluation?") are not hijacked.
        if "qa model" in q:
            return any(
                t in q for t in ("pam", "you", "using", "running", "current", "system", "installed")
            )
        return False

    def _match_capabilities(self, q: str) -> bool:
        if not any(t in q for t in ("ingest", "support", "process")):
            return False
        return any(
            t in q for t in ("types", "formats", "extensions", "file types", "what can", "files do")
        )

    def _match_source_count(self, q: str) -> bool:
        if not self._HOW_MANY_RE.search(q):
            return False
        if not re.search(r"\b(documents|sources|files|notes)\b", q):
            return False
        return any(
            t in q
            for t in (
                "indexed",
                "ingested",
                "stored",
                "loaded",
                "in the kb",
                "in the knowledge base",
            )
        )

    def _match_chunk_count(self, q: str) -> bool:
        if not self._HOW_MANY_RE.search(q):
            return False
        if not re.search(r"\b(chunks|vectors|embeddings)\b", q):
            return False
        return any(t in q for t in ("indexed", "stored", "there", "in the"))

    def _match_status(self, q: str) -> bool:
        if "status" in q and "pam" in q:
            return True
        if "system health" in q:
            return True
        return "health" in q and "ok" in q


class SystemFactsService:
    """Collect deterministic system facts from authoritative PAM state."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._version = self._read_version()
        self._manifest = ManifestManager(
            settings.manifest.path,
            project_root=settings.paths.project_root,
            enabled=settings.manifest.enabled,
        )

    def resolve(self, intent: Intent) -> SystemFact:
        if intent == Intent.VERSION:
            return self._fact_version()
        if intent == Intent.SOURCE_COUNT:
            return self._fact_source_count()
        if intent == Intent.CHUNK_COUNT:
            return self._fact_chunk_count()
        if intent == Intent.FEATURE_STATUS:
            return self._fact_feature_status()
        if intent == Intent.QA_MODEL:
            return self._fact_qa_model()
        if intent == Intent.CAPABILITIES:
            return self._fact_capabilities()
        if intent == Intent.STATUS:
            return self._fact_status()
        raise ValueError(f"Unknown system-facts intent: {intent}")

    def _read_version(self) -> str:
        """Read the authoritative application version from pyproject.toml."""
        project_root = self._settings.paths.project_root
        candidates = (project_root / "pyproject.toml", project_root / ".." / "pyproject.toml")
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.exists():
                try:
                    with resolved.open("rb") as fh:
                        project = tomllib.load(fh)
                    version = project.get("project", {}).get("version")
                    if version:
                        return str(version)
                except (tomllib.TOMLDecodeError, OSError):
                    pass
        return "unknown"

    def _fact_version(self) -> SystemFact:
        return SystemFact(
            intent=Intent.VERSION,
            label="PAM version",
            value=f"Personal AI Memory v{self._version}",
            detail=f"app={self._settings.app.name}, environment={self._settings.app.environment}",
        )

    def _store_counts(self) -> tuple[int | None, int | None]:
        """Return (distinct_sources, chunks) or (None, None) if unreadable."""
        store_path = self._settings.paths.manifest_root / VECTOR_STORE_FILENAME
        if not store_path.exists():
            return None, None
        try:
            data = json.loads(store_path.read_text(encoding="utf-8"))
            entries = data.get("entries", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, OSError):
            return None, None
        if not isinstance(entries, list):
            return None, None
        sources = len({e.get("source", "") for e in entries if isinstance(e, dict)})
        return sources, len(entries)

    def _fact_source_count(self) -> SystemFact:
        sources, _chunks = self._store_counts()
        value = str(sources) if sources is not None else "unavailable"
        return SystemFact(
            intent=Intent.SOURCE_COUNT,
            label="Indexed sources",
            value=f"{value} source(s) indexed",
            detail="vector store",
        )

    def _fact_chunk_count(self) -> SystemFact:
        _sources, chunks = self._store_counts()
        value = str(chunks) if chunks is not None else "unavailable"
        return SystemFact(
            intent=Intent.CHUNK_COUNT,
            label="Indexed chunks",
            value=f"{value} chunk(s) indexed",
            detail="vector store",
        )

    def _fact_feature_status(self) -> SystemFact:
        flags = {
            "reranker": self._settings.reranker.enabled,
            "HyDE": self._settings.hyde.enabled,
            "answerability": self._settings.answerability.enabled,
        }
        enabled = [name for name, on in flags.items() if on]
        value = ", ".join(enabled) if enabled else "none"
        return SystemFact(
            intent=Intent.FEATURE_STATUS,
            label="Feature flags",
            value=f"enabled: {value}",
            detail="all remaining experimental features off; retrieval V1 frozen",
        )

    def _fact_qa_model(self) -> SystemFact:
        return SystemFact(
            intent=Intent.QA_MODEL,
            label="QA model",
            value=f"QA model: {self._settings.ollama.model}",
            detail=(
                f"embeddings={self._settings.models.embeddings}, "
                f"qa_timeout={self._settings.qa.timeout_seconds}s, "
                f"ollama_num_ctx={OLLAMA_NUM_CTX}"
            ),
        )

    def _fact_capabilities(self) -> SystemFact:
        return SystemFact(
            intent=Intent.CAPABILITIES,
            label="Ingestion capabilities",
            value="PAM can ingest: " + SUPPORTED_INGESTION_TYPES,
            detail=f"{len(self._settings.watcher.supported_extensions)} supported file extensions",
        )

    def _fact_status(self) -> SystemFact:
        processed = sum(1 for e in self._manifest.list_entries() if e.status == "processed")
        skipped = sum(1 for e in self._manifest.list_entries() if e.status == "skipped_duplicate")
        failed = sum(1 for e in self._manifest.list_entries() if e.status == "failed")
        sources, chunks = self._store_counts()
        src = str(sources) if sources is not None else "unavailable"
        chk = str(chunks) if chunks is not None else "unavailable"
        return SystemFact(
            intent=Intent.STATUS,
            label="PAM status",
            value=(
                f"PAM is running (v{self._version}). Indexed {src} sources / {chk} chunks. "
                f"And {processed} successful ingests, {skipped} skipped, {failed} failed."
            ),
            detail=(
                f"feature flags off; retrieval V1 frozen; "
                f"QA model={self._settings.ollama.model}"
            ),
        )
