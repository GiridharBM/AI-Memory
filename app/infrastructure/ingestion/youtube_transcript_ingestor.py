"""YouTube transcript ingestor."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import BaseIngestor, IngestionError, SourceReference
from app.infrastructure.ingestion.utils import clean_text

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
_TRANSCRIPT_LANGUAGES = ["en", "en-US", "en-GB"]


class YouTubeTranscriptIngestor(BaseIngestor):
    """Download and normalize transcripts for YouTube videos."""

    source_type = "youtube_transcript"
    supported_suffixes = ()

    def __init__(self) -> None:
        self._client = YouTubeTranscriptApi()

    def can_ingest(self, source: SourceReference) -> bool:
        if not isinstance(source, str):
            return False

        parsed = urlparse(source)
        return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in _YOUTUBE_HOSTS

    def ingest(self, source: SourceReference) -> SourceDocument:
        if not isinstance(source, str):
            raise IngestionError(
                f"YouTube transcript ingestor received unsupported source reference '{source}'."
            )

        video_id = _extract_video_id(source)

        try:
            transcript = self._client.fetch(video_id, languages=_TRANSCRIPT_LANGUAGES)
        except Exception as exc:
            raise _map_transcript_exception(source, exc) from exc

        raw_snippets = transcript.to_raw_data()
        text = clean_text("\n".join(_snippet_text(snippet) for snippet in raw_snippets))
        if not text:
            raise IngestionError(f"YouTube video '{source}' returned an empty transcript.")

        transcript_language = getattr(transcript, "language", None)
        transcript_language_code = getattr(transcript, "language_code", None)
        is_generated = getattr(transcript, "is_generated", None)
        resolved_video_id = getattr(transcript, "video_id", video_id)

        title = f"YouTube Transcript - {resolved_video_id}"
        return SourceDocument(
            source=source,
            source_path=None,
            source_type=self.source_type,
            filename=f"{resolved_video_id}.transcript.md",
            text=text,
            metadata=DocumentMetadata(
                title=title,
                modified_at=datetime.now(tz=UTC),
                mime_type="text/plain",
                encoding="utf-8",
                extra={
                    "video_id": resolved_video_id,
                    "language": transcript_language,
                    "language_code": transcript_language_code,
                    "is_generated": is_generated,
                    "snippet_count": len(raw_snippets),
                    "downloaded_at": datetime.now(tz=UTC).isoformat(),
                },
            ),
        )


def _extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
        if video_id:
            return video_id

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
            if video_id:
                return video_id

        path_parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in {"embed", "shorts", "live", "v"}:
            return path_parts[1]

    raise IngestionError(f"Unable to extract a YouTube video ID from '{url}'.")


def _map_transcript_exception(source: str, exc: Exception) -> IngestionError:
    class_name = exc.__class__.__name__
    if class_name in {"NoTranscriptFound", "TranscriptsDisabled"}:
        return IngestionError(f"No transcript is available for YouTube video '{source}'.")
    if class_name == "VideoUnavailable":
        return IngestionError(f"YouTube video '{source}' is unavailable.")
    if class_name in {"YouTubeRequestFailed", "IpBlocked", "RequestBlocked"}:
        return IngestionError(f"Failed to download transcript for YouTube video '{source}'.")
    return IngestionError(f"Unable to retrieve transcript for YouTube video '{source}'.")


def _snippet_text(snippet: object) -> str:
    if isinstance(snippet, dict):
        text = snippet.get("text")
        return text if isinstance(text, str) else ""

    text = getattr(snippet, "text", "")
    return text if isinstance(text, str) else ""
