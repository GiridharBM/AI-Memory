"""Tests for the content classifier."""

from __future__ import annotations

from pathlib import Path

from app.core.extensions import PROCESSABLE_EXTENSIONS
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.routing.classifier import (
    EXTENSION_KIND_MAP,
    DocumentClassifier,
)


def _doc(filename: str, source_type: str, text: str = "") -> SourceDocument:
    return SourceDocument(
        source=filename,
        source_path=Path(filename),
        source_type=source_type,
        filename=filename,
        text=text,
        metadata=DocumentMetadata(),
    )


class TestClassifierFileTypes:
    def setup_method(self) -> None:
        self.classifier = DocumentClassifier()

    def test_markdown_detection(self) -> None:
        kind = self.classifier._detect_kind(".md", "markdown")
        assert kind == "markdown"

    def test_every_mapped_extension_classifies_to_its_kind(self) -> None:
        for ext, kind in EXTENSION_KIND_MAP.items():
            detected = self.classifier._detect_kind(ext, "")
            assert detected == kind, f"{ext} -> {detected}, expected {kind}"

    def test_all_processable_extensions_are_mapped(self) -> None:
        unmapped = PROCESSABLE_EXTENSIONS - set(EXTENSION_KIND_MAP)
        assert unmapped == set()

    def test_markdown_variant_detection(self) -> None:
        kind = self.classifier._detect_kind(".markdown", "markdown")
        assert kind == "markdown"

    def test_text_detection(self) -> None:
        kind = self.classifier._detect_kind(".txt", "text")
        assert kind == "text"

    def test_pdf_detection(self) -> None:
        kind = self.classifier._detect_kind(".pdf", "pdf")
        assert kind == "pdf"

    def test_code_python(self) -> None:
        kind = self.classifier._detect_kind(".py", "code")
        assert kind == "code"

    def test_code_javascript(self) -> None:
        kind = self.classifier._detect_kind(".js", "code")
        assert kind == "code"

    def test_code_typescript(self) -> None:
        kind = self.classifier._detect_kind(".ts", "code")
        assert kind == "code"

    def test_code_java(self) -> None:
        kind = self.classifier._detect_kind(".java", "code")
        assert kind == "code"

    def test_code_go(self) -> None:
        kind = self.classifier._detect_kind(".go", "code")
        assert kind == "code"

    def test_code_rust(self) -> None:
        kind = self.classifier._detect_kind(".rs", "code")
        assert kind == "code"

    def test_csv_detection(self) -> None:
        kind = self.classifier._detect_kind(".csv", "csv")
        assert kind == "csv"

    def test_tsv_detection(self) -> None:
        kind = self.classifier._detect_kind(".tsv", "csv")
        assert kind == "csv"

    def test_excel_detection(self) -> None:
        kind = self.classifier._detect_kind(".xlsx", "spreadsheet")
        assert kind == "spreadsheet"

    def test_image_png(self) -> None:
        kind = self.classifier._detect_kind(".png", "image")
        assert kind == "image"

    def test_image_jpg(self) -> None:
        kind = self.classifier._detect_kind(".jpg", "image")
        assert kind == "image"

    def test_image_webp(self) -> None:
        kind = self.classifier._detect_kind(".webp", "image")
        assert kind == "image"

    def test_audio_mp3(self) -> None:
        kind = self.classifier._detect_kind(".mp3", "audio")
        assert kind == "audio"

    def test_audio_wav(self) -> None:
        kind = self.classifier._detect_kind(".wav", "audio")
        assert kind == "audio"

    def test_audio_flac(self) -> None:
        kind = self.classifier._detect_kind(".flac", "audio")
        assert kind == "audio"

    def test_video_mp4(self) -> None:
        kind = self.classifier._detect_kind(".mp4", "video")
        assert kind == "video"

    def test_video_mkv(self) -> None:
        kind = self.classifier._detect_kind(".mkv", "video")
        assert kind == "video"

    def test_docx_detection(self) -> None:
        kind = self.classifier._detect_kind(".docx", "docx")
        assert kind == "docx"

    def test_pptx_detection(self) -> None:
        kind = self.classifier._detect_kind(".pptx", "pptx")
        assert kind == "pptx"

    def test_unknown_extension(self) -> None:
        kind = self.classifier._detect_kind(".xyz", "unknown")
        assert kind == "unknown"


class TestClassifierNewFileTypes:
    """Tests for all newly supported file types."""

    def setup_method(self) -> None:
        self.classifier = DocumentClassifier()

    # ── Documents ────────────────────────────────────────────────────────
    def test_rtf_detection(self) -> None:
        kind = self.classifier._detect_kind(".rtf", "text")
        assert kind == "docx"

    def test_odt_detection(self) -> None:
        kind = self.classifier._detect_kind(".odt", "text")
        assert kind == "docx"

    def test_tex_detection(self) -> None:
        kind = self.classifier._detect_kind(".tex", "text")
        assert kind == "tex"

    def test_epub_detection(self) -> None:
        kind = self.classifier._detect_kind(".epub", "text")
        assert kind == "epub"

    # ── Programming ─────────────────────────────────────────────────────
    def test_code_jsx(self) -> None:
        kind = self.classifier._detect_kind(".jsx", "code")
        assert kind == "code"

    def test_code_tsx(self) -> None:
        kind = self.classifier._detect_kind(".tsx", "code")
        assert kind == "code"

    def test_code_kotlin(self) -> None:
        kind = self.classifier._detect_kind(".kt", "code")
        assert kind == "code"

    def test_code_swift(self) -> None:
        kind = self.classifier._detect_kind(".swift", "code")
        assert kind == "code"

    def test_code_dart(self) -> None:
        kind = self.classifier._detect_kind(".dart", "code")
        assert kind == "code"

    def test_code_scala(self) -> None:
        kind = self.classifier._detect_kind(".scala", "code")
        assert kind == "code"

    def test_code_r(self) -> None:
        kind = self.classifier._detect_kind(".r", "code")
        assert kind == "code"

    def test_code_matlab(self) -> None:
        kind = self.classifier._detect_kind(".m", "code")
        assert kind == "code"

    def test_code_powershell(self) -> None:
        kind = self.classifier._detect_kind(".ps1", "code")
        assert kind == "code"

    def test_code_sql(self) -> None:
        kind = self.classifier._detect_kind(".sql", "code")
        assert kind == "code"

    def test_code_css(self) -> None:
        kind = self.classifier._detect_kind(".css", "code")
        assert kind == "code"

    def test_code_scss(self) -> None:
        kind = self.classifier._detect_kind(".scss", "code")
        assert kind == "code"

    def test_code_less(self) -> None:
        kind = self.classifier._detect_kind(".less", "code")
        assert kind == "code"

    def test_code_vue(self) -> None:
        kind = self.classifier._detect_kind(".vue", "code")
        assert kind == "code"

    def test_code_svelte(self) -> None:
        kind = self.classifier._detect_kind(".svelte", "code")
        assert kind == "code"

    def test_code_toml(self) -> None:
        kind = self.classifier._detect_kind(".toml", "code")
        assert kind == "config"

    def test_code_ini(self) -> None:
        kind = self.classifier._detect_kind(".ini", "code")
        assert kind == "config"

    def test_code_cfg(self) -> None:
        kind = self.classifier._detect_kind(".cfg", "code")
        assert kind == "config"

    def test_code_conf(self) -> None:
        kind = self.classifier._detect_kind(".conf", "code")
        assert kind == "config"

    def test_code_env(self) -> None:
        kind = self.classifier._detect_kind(".env", "code")
        assert kind == "config"

    def test_code_mermaid(self) -> None:
        kind = self.classifier._detect_kind(".mmd", "diagram")
        assert kind == "diagram"

    # ── Notebook ────────────────────────────────────────────────────────
    def test_notebook_detection(self) -> None:
        kind = self.classifier._detect_kind(".ipynb", "notebook")
        assert kind == "notebook"

    # ── Spreadsheet ─────────────────────────────────────────────────────
    def test_ods_detection(self) -> None:
        kind = self.classifier._detect_kind(".ods", "spreadsheet")
        assert kind == "spreadsheet"

    def test_xls_detection(self) -> None:
        kind = self.classifier._detect_kind(".xls", "spreadsheet")
        assert kind == "spreadsheet"

    # ── Presentation ────────────────────────────────────────────────────
    def test_ppt_detection(self) -> None:
        kind = self.classifier._detect_kind(".ppt", "pptx")
        assert kind == "pptx"

    def test_odp_detection(self) -> None:
        kind = self.classifier._detect_kind(".odp", "pptx")
        assert kind == "pptx"

    # ── Image ───────────────────────────────────────────────────────────
    def test_image_heic(self) -> None:
        kind = self.classifier._detect_kind(".heic", "image")
        assert kind == "image"

    def test_image_svg(self) -> None:
        kind = self.classifier._detect_kind(".svg", "image")
        assert kind == "image"

    def test_image_bmp(self) -> None:
        kind = self.classifier._detect_kind(".bmp", "image")
        assert kind == "image"

    def test_image_tiff(self) -> None:
        kind = self.classifier._detect_kind(".tiff", "image")
        assert kind == "image"

    def test_image_gif(self) -> None:
        kind = self.classifier._detect_kind(".gif", "image")
        assert kind == "image"

    # ── Diagram ─────────────────────────────────────────────────────────
    def test_diagram_drawio(self) -> None:
        kind = self.classifier._detect_kind(".drawio", "diagram")
        assert kind == "diagram"

    def test_diagram_vsdx(self) -> None:
        kind = self.classifier._detect_kind(".vsdx", "diagram")
        assert kind == "diagram"

    # ── Audio ───────────────────────────────────────────────────────────
    def test_audio_aac(self) -> None:
        kind = self.classifier._detect_kind(".aac", "audio")
        assert kind == "audio"

    def test_audio_ogg(self) -> None:
        kind = self.classifier._detect_kind(".ogg", "audio")
        assert kind == "audio"

    # ── Video ───────────────────────────────────────────────────────────
    def test_video_avi(self) -> None:
        kind = self.classifier._detect_kind(".avi", "video")
        assert kind == "video"

    def test_video_webm(self) -> None:
        kind = self.classifier._detect_kind(".webm", "video")
        assert kind == "video"

    # ── Archive ─────────────────────────────────────────────────────────
    def test_archive_zip(self) -> None:
        kind = self.classifier._detect_kind(".zip", "archive")
        assert kind == "archive"

    def test_archive_tar(self) -> None:
        kind = self.classifier._detect_kind(".tar", "archive")
        assert kind == "archive"

    def test_archive_gz(self) -> None:
        kind = self.classifier._detect_kind(".gz", "archive")
        assert kind == "archive"

    def test_archive_7z(self) -> None:
        kind = self.classifier._detect_kind(".7z", "archive")
        assert kind == "archive"

    def test_archive_rar(self) -> None:
        kind = self.classifier._detect_kind(".rar", "archive")
        assert kind == "archive"

    # ── Email ───────────────────────────────────────────────────────────
    def test_email_eml(self) -> None:
        kind = self.classifier._detect_kind(".eml", "email")
        assert kind == "email"

    def test_email_msg(self) -> None:
        kind = self.classifier._detect_kind(".msg", "email")
        assert kind == "email"

    # ── Database ────────────────────────────────────────────────────────
    def test_database_sqlite(self) -> None:
        kind = self.classifier._detect_kind(".sqlite", "database")
        assert kind == "database"

    def test_database_db(self) -> None:
        kind = self.classifier._detect_kind(".db", "database")
        assert kind == "database"

    # ── Research ────────────────────────────────────────────────────────
    def test_research_bib(self) -> None:
        kind = self.classifier._detect_kind(".bib", "research")
        assert kind == "research"

    def test_research_ris(self) -> None:
        kind = self.classifier._detect_kind(".ris", "research")
        assert kind == "research"

    # ── Web ─────────────────────────────────────────────────────────────
    def test_web_html(self) -> None:
        kind = self.classifier._detect_kind(".html", "text")
        assert kind == "web"

    def test_web_htm(self) -> None:
        kind = self.classifier._detect_kind(".htm", "text")
        assert kind == "web"

    def test_web_xml(self) -> None:
        kind = self.classifier._detect_kind(".xml", "text")
        assert kind == "web"

    def test_web_json(self) -> None:
        kind = self.classifier._detect_kind(".json", "text")
        assert kind == "web"

    def test_web_rss(self) -> None:
        kind = self.classifier._detect_kind(".rss", "text")
        assert kind == "web"


class TestClassifierClassify:
    def setup_method(self) -> None:
        self.classifier = DocumentClassifier()

    def test_classify_markdown(self) -> None:
        doc = _doc("readme.md", "markdown")
        result = self.classifier.classify(doc)
        assert result.kind == "markdown"
        assert result.extension == ".md"
        assert result.confidence == 0.92

    def test_classify_code(self) -> None:
        doc = _doc("main.py", "code")
        result = self.classifier.classify(doc)
        assert result.kind == "code"
        assert result.requires_code_parsing is True

    def test_classify_image(self) -> None:
        doc = _doc("photo.png", "image")
        result = self.classifier.classify(doc)
        assert result.kind == "image"
        assert result.requires_ocr is True
        assert result.requires_vision is True

    def test_classify_audio(self) -> None:
        doc = _doc("speech.mp3", "audio")
        result = self.classifier.classify(doc)
        assert result.kind == "audio"

    def test_classify_video(self) -> None:
        doc = _doc("clip.mp4", "video")
        result = self.classifier.classify(doc)
        assert result.kind == "video"
        assert result.requires_vision is True

    def test_classify_csv(self) -> None:
        doc = _doc("data.csv", "csv")
        result = self.classifier.classify(doc)
        assert result.kind == "csv"
        assert result.requires_table_extraction is True

    def test_classify_xlsx(self) -> None:
        doc = _doc("report.xlsx", "spreadsheet")
        result = self.classifier.classify(doc)
        assert result.kind == "spreadsheet"
        assert result.requires_table_extraction is True

    def test_classify_docx(self) -> None:
        doc = _doc("letter.docx", "docx")
        result = self.classifier.classify(doc)
        assert result.kind == "docx"

    def test_classify_pptx(self) -> None:
        doc = _doc("slides.pptx", "pptx")
        result = self.classifier.classify(doc)
        assert result.kind == "pptx"

    def test_classify_notebook(self) -> None:
        doc = _doc("analysis.ipynb", "notebook")
        result = self.classifier.classify(doc)
        assert result.kind == "notebook"

    def test_classify_archive(self) -> None:
        doc = _doc("backup.zip", "archive")
        result = self.classifier.classify(doc)
        assert result.kind == "archive"

    def test_classify_email(self) -> None:
        doc = _doc("message.eml", "email")
        result = self.classifier.classify(doc)
        assert result.kind == "email"

    def test_classify_database(self) -> None:
        doc = _doc("data.sqlite", "database")
        result = self.classifier.classify(doc)
        assert result.kind == "database"

    def test_classify_research(self) -> None:
        doc = _doc("refs.bib", "research")
        result = self.classifier.classify(doc)
        assert result.kind == "research"

    def test_classify_diagram(self) -> None:
        doc = _doc("arch.drawio", "diagram")
        result = self.classifier.classify(doc)
        assert result.kind == "diagram"

    def test_classify_tex(self) -> None:
        doc = _doc("paper.tex", "text")
        result = self.classifier.classify(doc)
        assert result.kind == "tex"

    def test_classify_epub(self) -> None:
        doc = _doc("book.epub", "text")
        result = self.classifier.classify(doc)
        assert result.kind == "epub"

    def test_classify_web(self) -> None:
        doc = _doc("page.html", "text")
        result = self.classifier.classify(doc)
        assert result.kind == "web"

    def test_classify_database_table_flag(self) -> None:
        doc = _doc("data.sqlite", "database")
        result = self.classifier.classify(doc)
        assert result.requires_table_extraction is True

    def test_classify_scanned_pdf(self) -> None:
        doc = _doc("scan.pdf", "scanned_pdf")
        result = self.classifier.classify(doc)
        assert result.kind == "scanned_pdf"
        assert result.requires_ocr is True

    def test_classify_handwritten(self) -> None:
        doc = _doc("notes.pdf", "handwritten")
        result = self.classifier.classify(doc)
        assert result.kind == "handwritten"
        assert result.requires_ocr is True
        assert result.requires_vision is True
