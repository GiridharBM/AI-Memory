"""Ingestor for EPUB ebook files (.epub)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.core.logging import get_logger
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import clean_text, file_timestamp

logger = get_logger(__name__)

_NS = {"n": "urn:oasis:names:tc:opendocument:xmlns:container"}


class EpubIngestor(BaseIngestor):
    """Ingest EPUB ebooks by extracting HTML content."""

    source_type = "epub"
    supported_suffixes = (".epub",)

    def ingest(self, source: SourceReference) -> SourceDocument:
        path = require_path_source(source, ingestor_name="EpubIngestor")
        if not zipfile.is_zipfile(path):
            raise IngestionError(f"File '{path.name}' is not a valid EPUB archive.")

        try:
            with zipfile.ZipFile(path, "r") as zf:
                # Find content.opf via META-INF/container.xml
                container_xml = zf.read("META-INF/container.xml")
                container_tree = ElementTree.fromstring(container_xml)
                rootfile_el = container_tree.find(".//n:rootfile", _NS)
                if rootfile_el is None:
                    raise IngestionError("Cannot locate rootfile in EPUB container.")
                opf_path = rootfile_el.get("full-path", "")

                # Parse OPF for metadata
                opf_xml = zf.read(opf_path)
                opf_tree = ElementTree.fromstring(opf_path)
                ns_opf = {"opf": "http://www.idpf.org/2007/opf"}
                opf_tree = ElementTree.fromstring(opf_xml)
                title_el = opf_tree.find(".//opf:title", ns_opf)
                title = title_el.text if title_el is not None else path.stem
                creator_el = opf_tree.find(".//opf:creator", ns_opf)
                author = creator_el.text if creator_el is not None else ""

                # Collect all HTML content
                parts: list[str] = []
                for item in opf_tree.findall(".//opf:item", ns_opf):
                    media_type = item.get("media-type", "")
                    href = item.get("href", "")
                    if "html" in media_type or href.endswith((".html", ".xhtml", ".htm")):
                        base_dir = Path(opf_path).parent
                        full_href = str(base_dir / href)
                        try:
                            html_content = zf.read(full_href).decode("utf-8", errors="replace")
                            # Strip HTML tags for plain text extraction
                            import re
                            text = re.sub(r"<[^>]+>", " ", html_content)
                            text = re.sub(r"\s+", " ", text).strip()
                            if text:
                                parts.append(text)
                        except KeyError:
                            continue

                cleaned = clean_text("\n\n".join(parts))
                return SourceDocument(
                    source=str(path),
                    source_path=path,
                    source_type=self.source_type,
                    filename=path.name,
                    text=cleaned,
                    metadata=DocumentMetadata(
                        title=str(title),
                        author=str(author),
                        created_at=file_timestamp(path),
                        modified_at=file_timestamp(path),
                    ),
                )
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError(f"Failed to process EPUB '{path.name}'.") from exc
