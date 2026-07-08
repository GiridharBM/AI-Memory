"""GitHub repository README ingestor."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import BaseIngestor, IngestionError, SourceReference
from app.infrastructure.ingestion.utils import clean_text

_REQUEST_TIMEOUT_SECONDS = 30


class GitHubReadmeIngestor(BaseIngestor):
    """Download and normalize the README for a GitHub repository URL."""

    source_type = "github_readme"
    supported_suffixes = ()

    def can_ingest(self, source: SourceReference) -> bool:
        if not isinstance(source, str):
            return False

        parsed = urlparse(source)
        path_parts = [part for part in parsed.path.strip("/").split("/") if part]
        return (
            parsed.scheme in {"http", "https"}
            and parsed.netloc.lower() == "github.com"
            and len(path_parts) >= 2
        )

    def ingest(self, source: SourceReference) -> SourceDocument:
        if not isinstance(source, str):
            raise IngestionError(
                f"GitHub README ingestor received unsupported source reference '{source}'."
            )

        owner, repository = _parse_repository_coordinates(source)
        metadata_payload = _fetch_json(_build_repo_api_url(owner, repository))
        readme_payload = _fetch_json(_build_readme_api_url(owner, repository))

        readme_content = _decode_readme_content(readme_payload)
        cleaned_text = clean_text(readme_content)
        if not cleaned_text:
            raise IngestionError(f"GitHub repository '{owner}/{repository}' README is empty.")

        filename = _string_or_none(readme_payload.get("name")) or "README.md"
        title = _string_or_none(metadata_payload.get("full_name")) or f"{owner}/{repository}"
        updated_at = _parse_iso_datetime(metadata_payload.get("updated_at"))

        return SourceDocument(
            source=source,
            source_path=None,
            source_type=self.source_type,
            filename=filename,
            text=cleaned_text,
            metadata=DocumentMetadata(
                title=title,
                author=_owner_login(metadata_payload),
                modified_at=updated_at,
                mime_type="text/markdown",
                encoding="utf-8",
                extra={
                    "repository_owner": owner,
                    "repository_name": repository,
                    "repository_full_name": metadata_payload.get("full_name"),
                    "repository_default_branch": metadata_payload.get("default_branch"),
                    "repository_description": metadata_payload.get("description"),
                    "readme_path": readme_payload.get("path"),
                    "downloaded_at": datetime.now(tz=UTC).isoformat(),
                },
            ),
        )


def _parse_repository_coordinates(repository_url: str) -> tuple[str, str]:
    parsed = urlparse(repository_url)
    if parsed.netloc.lower() != "github.com":
        raise IngestionError(f"Unsupported repository host in URL '{repository_url}'.")

    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(path_parts) < 2:
        raise IngestionError(
            f"GitHub repository URL '{repository_url}' is missing owner or repository name."
        )

    owner = path_parts[0]
    repository = path_parts[1]
    if repository.endswith(".git"):
        repository = repository[:-4]

    if not owner or not repository:
        raise IngestionError(f"GitHub repository URL '{repository_url}' is invalid.")

    return owner, repository


def _build_repo_api_url(owner: str, repository: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repository}"


def _build_readme_api_url(owner: str, repository: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repository}/readme"


def _fetch_json(url: str) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "personal-ai-memory",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise IngestionError(f"GitHub resource not found: {url}") from exc
        raise IngestionError(f"GitHub request failed with status code {exc.code}.") from exc
    except URLError as exc:
        raise IngestionError(f"Unable to reach GitHub for URL '{url}'.") from exc
    except TimeoutError as exc:
        raise IngestionError(f"GitHub request timed out for URL '{url}'.") from exc
    except json.JSONDecodeError as exc:
        raise IngestionError(f"GitHub returned invalid JSON for URL '{url}'.") from exc

    if not isinstance(payload, dict):
        raise IngestionError(f"GitHub returned an unexpected payload for URL '{url}'.")

    return payload


def _decode_readme_content(payload: dict[str, object]) -> str:
    encoded_content = payload.get("content")
    if not isinstance(encoded_content, str):
        raise IngestionError("GitHub README response did not include file content.")

    try:
        decoded_bytes = base64.b64decode(encoded_content, validate=False)
    except ValueError as exc:
        raise IngestionError("Unable to decode GitHub README content.") from exc

    try:
        return decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionError("GitHub README content is not valid UTF-8 Markdown.") from exc


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _owner_login(payload: dict[str, object]) -> str | None:
    owner = payload.get("owner")
    if not isinstance(owner, dict):
        return None
    login = owner.get("login")
    return login if isinstance(login, str) else None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
