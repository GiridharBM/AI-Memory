"""Semantic chunking for knowledge engine."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.logging import get_logger
from app.domain.semantic_chunking import DocumentChunk

logger = get_logger(__name__)

_HEADING_PATTERN = re.compile(r"^#{1,6}\s+.+", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\d])")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


@dataclass
class SemanticChunker:
    """Split text into semantic chunks by headings, then by max size."""

    max_chunk_chars: int = 2000
    overlap_chars: int = 200

    def chunk(
        self,
        text: str,
        source: str,
        source_type: str,
    ) -> list[DocumentChunk]:
        if not text.strip():
            return []

        sections = self._split_by_headings(text)
        chunks: list[DocumentChunk] = []
        chunk_index = 0

        for section_start, section_text in sections:
            if len(section_text) <= self.max_chunk_chars:
                chunks.append(DocumentChunk(
                    chunk_id=f"{source}::chunk_{chunk_index}",
                    text=section_text.strip(),
                    source=source,
                    source_type=source_type,
                    chunk_index=chunk_index,
                    start_char=section_start,
                    end_char=section_start + len(section_text),
                ))
                chunk_index += 1
            else:
                sub_chunks = self._split_long_section(section_text, section_start)
                for start, end, sub_text in sub_chunks:
                    chunks.append(DocumentChunk(
                        chunk_id=f"{source}::chunk_{chunk_index}",
                        text=sub_text.strip(),
                        source=source,
                        source_type=source_type,
                        chunk_index=chunk_index,
                        start_char=start,
                        end_char=end,
                    ))
                    chunk_index += 1

        chunks = self._apply_overlap(chunks)

        logger.debug(
            "Document chunked.",
            extra={"source": source, "chunks": len(chunks), "text_length": len(text)},
        )
        return chunks

    def _apply_overlap(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Prepend the previous chunk's tail to each chunk after the first."""
        if self.overlap_chars <= 0 or len(chunks) < 2:
            return chunks

        overlapped: list[DocumentChunk] = []
        for index, chunk in enumerate(chunks):
            text = chunk.text
            if index > 0:
                text = overlapped[index - 1].text[-self.overlap_chars:] + text
            overlapped.append(DocumentChunk(
                chunk_id=chunk.chunk_id,
                text=text,
                source=chunk.source,
                source_type=chunk.source_type,
                chunk_index=chunk.chunk_index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                metadata=chunk.metadata,
            ))
        return overlapped

    def _split_by_headings(self, text: str) -> list[tuple[int, str]]:
        positions = [m.start() for m in _HEADING_PATTERN.finditer(text)]
        if not positions:
            return [(0, text)]

        sections: list[tuple[int, str]] = []
        if positions[0] > 0:
            sections.append((0, text[:positions[0]]))

        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            sections.append((pos, text[pos:end]))

        return sections

    def _split_long_section(
        self, text: str, base_offset: int,
    ) -> list[tuple[int, int, str]]:
        paragraphs = _PARAGRAPH_SPLIT.split(text)
        result: list[tuple[int, int, str]] = []
        current = ""
        current_start = base_offset

        for para in paragraphs:
            if len(current) + len(para) + 2 <= self.max_chunk_chars:
                current = f"{current}\n\n{para}" if current else para
            else:
                if current:
                    result.append((current_start, current_start + len(current), current))
                    current_start += len(current)
                if len(para) > self.max_chunk_chars:
                    sentence_chunks = self._split_by_sentences(para, current_start)
                    result.extend(sentence_chunks)
                    for _, end, txt in sentence_chunks:
                        current_start = end
                    current = ""
                else:
                    current = para

        if current:
            result.append((current_start, current_start + len(current), current))

        return result

    def _split_by_sentences(
        self, text: str, base_offset: int,
    ) -> list[tuple[int, int, str]]:
        sentences = _SENTENCE_END.split(text)
        result: list[tuple[int, int, str]] = []
        current = ""
        offset = base_offset

        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= self.max_chunk_chars:
                current = f"{current} {sentence}" if current else sentence
            else:
                if current:
                    result.append((offset, offset + len(current), current))
                    offset += len(current)
                current = sentence

        if current:
            result.append((offset, offset + len(current), current))

        return result
