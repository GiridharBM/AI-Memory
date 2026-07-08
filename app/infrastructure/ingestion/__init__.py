"""Source ingestion adapters."""

from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    UnsupportedSourceError,
)
from app.infrastructure.ingestion.github_readme_ingestor import GitHubReadmeIngestor
from app.infrastructure.ingestion.markdown_ingestor import MarkdownIngestor
from app.infrastructure.ingestion.pdf_ingestor import PdfIngestor
from app.infrastructure.ingestion.service import DocumentIngestionService
from app.infrastructure.ingestion.txt_ingestor import TextIngestor
from app.infrastructure.ingestion.youtube_transcript_ingestor import YouTubeTranscriptIngestor

__all__ = [
    "BaseIngestor",
    "DocumentIngestionService",
    "GitHubReadmeIngestor",
    "IngestionError",
    "MarkdownIngestor",
    "PdfIngestor",
    "SourceReference",
    "TextIngestor",
    "UnsupportedSourceError",
    "YouTubeTranscriptIngestor",
]
