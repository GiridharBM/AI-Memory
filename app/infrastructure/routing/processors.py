"""Built-in processor registrations."""

from __future__ import annotations

from app.infrastructure.routing.router import RoutedProcessor


def default_processors() -> list[RoutedProcessor]:
    """Return all registered processors with their kind-to-model mappings.

    Model routing keys map to ModelRoutingSettings fields:
      - general_text  → qwen3:8b
      - programming   → qwen2.5-coder:7b
      - vision        → qwen2.5vl:7b
      - scanned_ocr   → qwen2.5vl:7b
      - handwriting_ocr → qwen2.5vl:7b
      - audio         → faster-whisper
    """
    return [
        # ── Text & Markup ────────────────────────────────────────────────
        RoutedProcessor("MarkdownProcessor", {"markdown"}, "general_text"),
        RoutedProcessor("WebProcessor", {"web", "html", "json", "xml"}, "general_text"),
        RoutedProcessor("TextProcessor", {"text", "unknown", "tex", "epub"}, "general_text"),
        # ── Code & Config ────────────────────────────────────────────────
        RoutedProcessor("CodeProcessor", {"code"}, "programming"),
        RoutedProcessor("ConfigProcessor", {"config"}, "general_text"),
        # ── Documents ────────────────────────────────────────────────────
        RoutedProcessor("PDFProcessor", {"pdf"}, "general_text"),
        RoutedProcessor("OCRProcessor", {"scanned_pdf"}, "scanned_ocr"),
        RoutedProcessor("HandwritingProcessor", {"handwritten"}, "handwriting_ocr"),
        RoutedProcessor("DocxProcessor", {"docx"}, "general_text"),
        RoutedProcessor("PptxProcessor", {"pptx"}, "general_text"),
        RoutedProcessor("ResearchProcessor", {"research"}, "general_text"),
        # ── Data ─────────────────────────────────────────────────────────
        RoutedProcessor("TableProcessor", {"csv", "spreadsheet"}, "general_text"),
        RoutedProcessor("DatabaseProcessor", {"database"}, "general_text"),
        RoutedProcessor("NotebookProcessor", {"notebook"}, "general_text"),
        # ── Media ────────────────────────────────────────────────────────
        RoutedProcessor("VisionProcessor", {"image"}, "vision"),
        RoutedProcessor("AudioProcessor", {"audio"}, "audio"),
        RoutedProcessor("VideoProcessor", {"video"}, "vision"),
        # ── Specialized ──────────────────────────────────────────────────
        RoutedProcessor("ArchiveProcessor", {"archive"}, "general_text"),
        RoutedProcessor("EmailProcessor", {"email"}, "general_text"),
        RoutedProcessor("DiagramProcessor", {"diagram"}, "general_text"),
    ]
