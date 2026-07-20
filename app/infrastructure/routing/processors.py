"""Built-in processor registrations."""

from __future__ import annotations

from app.infrastructure.routing.router import RoutedProcessor


def default_processors() -> list[RoutedProcessor]:
    return [
        RoutedProcessor("MarkdownProcessor", {"markdown"}, "general_text"),
        RoutedProcessor("CodeProcessor", {"code"}, "programming"),
        RoutedProcessor("PDFProcessor", {"pdf"}, "general_text"),
        RoutedProcessor("OCRProcessor", {"scanned_pdf"}, "scanned_ocr"),
        RoutedProcessor("HandwritingProcessor", {"handwritten"}, "handwriting_ocr"),
        RoutedProcessor("VisionProcessor", {"image"}, "vision"),
        RoutedProcessor("TableProcessor", {"csv", "spreadsheet"}, "general_text"),
        RoutedProcessor("AudioProcessor", {"audio"}, "audio"),
        RoutedProcessor("VideoProcessor", {"video"}, "vision"),
        RoutedProcessor("DocxProcessor", {"docx"}, "general_text"),
        RoutedProcessor("PptxProcessor", {"pptx"}, "general_text"),
        RoutedProcessor("TextProcessor", {"text", "html", "json", "xml", "unknown"}, "general_text"),
    ]
