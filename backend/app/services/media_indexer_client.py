"""Media Indexer HTTP client.

This client communicates with the Media Indexer public APIs over HTTP.
It does NOT access the Media Indexer database, filesystem, or internal services directly.
"""
import time
from uuid import UUID

import httpx

from app.core.config import settings
from app.core.logging import roteirista_logger
from app.schemas.media_indexer import (
    GameAnalysisMediaContext,
    MediaIndexerAlignment,
    MediaIndexerNote,
    MediaIndexerSearchResult,
    MediaIndexerSession,
    MediaIndexerTimelineNote,
    MediaIndexerTimelineSession,
)


class MediaIndexerError(Exception):
    """Base exception for Media Indexer client errors."""
    pass


class MediaIndexerUnavailableError(MediaIndexerError):
    """Media Indexer service is unavailable."""
    pass


class MediaIndexerNotFoundError(MediaIndexerError):
    """Resource not found in Media Indexer."""
    pass


class MediaIndexerConflictError(MediaIndexerError):
    """Conflict in Media Indexer (e.g., no suitable temporal index)."""
    pass


class MediaIndexerClient:
    """HTTP client for Media Indexer public APIs.

    Usage:
        client = MediaIndexerClient()
        sessions = await client.list_sessions(project_id)
        timeline = await client.get_semantic_timeline(session_id, temporal_index_id)
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        api_key: str | None = None,
    ):
        self.base_url = (base_url or settings.media_indexer_base_url).rstrip("/")
        self.timeout = timeout_seconds or settings.media_indexer_timeout_seconds
        self.api_key = api_key or settings.media_indexer_api_key

    def _get_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        """Make an HTTP request to Media Indexer."""
        url = f"{self.base_url}{path}"
        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._get_headers(),
                    **kwargs,
                )

                duration = time.time() - start_time
                roteirista_logger.logger.info(
                    "media_indexer_request",
                    extra={
                        "method": method,
                        "path": path,
                        "status_code": response.status_code,
                        "duration_seconds": round(duration, 3),
                    },
                )

                if response.status_code == 404:
                    raise MediaIndexerNotFoundError(f"Resource not found: {path}")
                if response.status_code == 409:
                    raise MediaIndexerConflictError(f"Conflict: {response.text}")
                if response.status_code >= 500:
                    raise MediaIndexerUnavailableError(
                        f"Media Indexer error: {response.status_code}"
                    )
                if response.status_code >= 400:
                    raise MediaIndexerError(f"Request failed: {response.status_code}")

                return response.json()

        except httpx.TimeoutException as e:
            duration = time.time() - start_time
            roteirista_logger.logger.warning(
                "media_indexer_timeout",
                extra={
                    "method": method,
                    "path": path,
                    "timeout_seconds": self.timeout,
                    "duration_seconds": round(duration, 3),
                },
            )
            raise MediaIndexerUnavailableError(f"Timeout: {e}") from e

        except httpx.ConnectError as e:
            roteirista_logger.logger.warning(
                "media_indexer_connection_failed",
                extra={"method": method, "path": path, "error": str(e)},
            )
            raise MediaIndexerUnavailableError(f"Connection failed: {e}") from e

        except httpx.HTTPError as e:
            raise MediaIndexerError(f"HTTP error: {e}") from e

    # =========================================================================
    # Project/Session endpoints
    # =========================================================================

    async def get_project(self, project_id: UUID) -> dict:
        """Get a project by ID."""
        return await self._request("GET", f"/projects/{project_id}")

    async def list_sessions(self, project_id: UUID) -> list[MediaIndexerSession]:
        """List all sessions in a project."""
        data = await self._request("GET", f"/projects/{project_id}/sessions")
        return [
            MediaIndexerSession(
                id=UUID(item["id"]),
                project_id=UUID(item["project_id"]),
                label=item["label"],
                status=item["status"],
            )
            for item in data
        ]

    async def get_session(self, session_id: UUID) -> dict:
        """Get a session by ID."""
        return await self._request("GET", f"/sessions/{session_id}")

    async def list_temporal_indexes(self, session_id: UUID) -> list[dict]:
        """List temporal indexes for a session."""
        return await self._request("GET", f"/sessions/{session_id}/temporal-indexes")

    # =========================================================================
    # Semantic Timeline endpoint
    # =========================================================================

    async def get_semantic_timeline(
        self,
        session_id: UUID,
        temporal_index_id: UUID,
        alignment_run_id: UUID | None = None,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> MediaIndexerTimelineSession:
        """Get the semantic timeline for a session.

        This retrieves notes with their alignment status and optional timestamps.
        """
        params = {
            "temporal_index_id": str(temporal_index_id),
            "offset": offset,
            "limit": limit,
        }
        if alignment_run_id:
            params["alignment_run_id"] = str(alignment_run_id)
        if start_seconds is not None:
            params["start_seconds"] = start_seconds
        if end_seconds is not None:
            params["end_seconds"] = end_seconds

        data = await self._request(
            "GET",
            f"/sessions/{session_id}/semantic-timeline",
            params=params,
        )

        # Extract session label from provenance
        session_label = data.get("provenance", {}).get("session_id", str(session_id))

        # Transform notes
        notes = []
        for note_data in data.get("notes", []):
            note = MediaIndexerNote(
                id=UUID(note_data["id"]),
                order=note_data["order"],
                raw=note_data["raw"],
                alignment_status=note_data["alignment_status"],
                alignment_subject_id=(
                    UUID(note_data["alignment_subject_id"])
                    if note_data.get("alignment_subject_id")
                    else None
                ),
            )

            alignment = None
            if note_data.get("selected_alignment"):
                align_data = note_data["selected_alignment"]
                alignment = MediaIndexerAlignment(
                    candidate_alignment_id=UUID(align_data["candidate_alignment_id"]),
                    retrieval_rank=align_data["retrieval_rank"],
                    start_seconds=align_data["start_seconds"],
                    end_seconds=align_data["end_seconds"],
                    confidence=align_data["confidence"],
                    reasoning_summary=align_data.get("reasoning_summary"),
                    timestamp_resolution_seconds=align_data.get("timestamp_resolution_seconds"),
                )

            notes.append(MediaIndexerTimelineNote(note=note, alignment=alignment))

        return MediaIndexerTimelineSession(
            session_id=session_id,
            session_label=session_label,
            notes=notes,
        )

    # =========================================================================
    # Media Search endpoint
    # =========================================================================

    async def search_session(
        self,
        session_id: UUID,
        query: str,
        max_results: int = 5,
        min_score: float = 0.25,
    ) -> list[MediaIndexerSearchResult]:
        """Search for footage within a session."""
        data = await self._request(
            "POST",
            f"/media-search/sessions/{session_id}",
            json={
                "query": query,
                "max_results": max_results,
                "min_score": min_score,
            },
        )

        results = []
        for item in data.get("results", []):
            results.append(
                MediaIndexerSearchResult(
                    session_id=UUID(item["session_id"]),
                    session_label=item["session_label"],
                    media_filename=item["media_filename"],
                    start_seconds=item["start_seconds"],
                    end_seconds=item["end_seconds"],
                    duration_seconds=item["duration_seconds"],
                    score=item["score"],
                    rank=item["rank"],
                    transcript_preview=item.get("transcript_preview"),
                )
            )

        return results

    async def search_project(
        self,
        project_id: UUID,
        query: str,
        max_results: int = 10,
        min_score: float = 0.25,
        session_ids: list[UUID] | None = None,
        exclude_session_ids: list[UUID] | None = None,
    ) -> list[MediaIndexerSearchResult]:
        """Search for footage across a project."""
        payload = {
            "query": query,
            "max_results": max_results,
            "min_score": min_score,
        }
        if session_ids:
            payload["session_ids"] = [str(sid) for sid in session_ids]
        if exclude_session_ids:
            payload["exclude_session_ids"] = [str(sid) for sid in exclude_session_ids]

        data = await self._request(
            "POST",
            f"/media-search/projects/{project_id}",
            json=payload,
        )

        results = []
        for item in data.get("results", []):
            results.append(
                MediaIndexerSearchResult(
                    session_id=UUID(item["session_id"]),
                    session_label=item["session_label"],
                    media_filename=item["media_filename"],
                    start_seconds=item["start_seconds"],
                    end_seconds=item["end_seconds"],
                    duration_seconds=item["duration_seconds"],
                    score=item["score"],
                    rank=item["rank"],
                    transcript_preview=item.get("transcript_preview"),
                )
            )

        return results


# Singleton instance
media_indexer_client = MediaIndexerClient()
