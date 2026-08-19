"""
Tests for MediaIndexerClient HTTP client.

Tests cover HTTP operations, error handling, and response parsing.
Uses mocks for HTTP operations - never makes real network calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import httpx

from app.services.media_indexer_client import (
    MediaIndexerClient,
    MediaIndexerError,
    MediaIndexerUnavailableError,
    MediaIndexerNotFoundError,
    MediaIndexerConflictError,
)
from app.schemas.media_indexer import (
    MediaIndexerSession,
    MediaIndexerTimelineSession,
    MediaIndexerSearchResult,
)


@pytest.fixture
def client():
    """Create a MediaIndexerClient instance for testing."""
    return MediaIndexerClient(
        base_url="http://test-media-indexer:8012",
        api_key="test-api-key",
        timeout_seconds=30,
    )


@pytest.fixture
def project_id():
    """Sample project ID."""
    return uuid4()


@pytest.fixture
def session_id():
    """Sample session ID."""
    return uuid4()


class TestMediaIndexerClientGetProject:
    """Tests for get_project method."""

    @pytest.mark.asyncio
    async def test_get_project_success(self, client, project_id):
        """Test successful project retrieval."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "id": str(project_id),
                "name": "Test Project",
                "slug": "test-project",
                "status": "active",
            }

            result = await client.get_project(project_id)

            assert result["name"] == "Test Project"
            mock_request.assert_called_once_with("GET", f"/projects/{project_id}")

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, client, project_id):
        """Test project not found error."""
        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = MediaIndexerNotFoundError("Not found")

            with pytest.raises(MediaIndexerNotFoundError):
                await client.get_project(project_id)


class TestMediaIndexerClientListSessions:
    """Tests for list_sessions method."""

    @pytest.mark.asyncio
    async def test_list_sessions_success(self, client, project_id):
        """Test successful session listing."""
        session_id = uuid4()
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = [
                {
                    "id": str(session_id),
                    "project_id": str(project_id),
                    "label": "Session 1",
                    "status": "ready",
                }
            ]

            result = await client.list_sessions(project_id)

            assert len(result) == 1
            assert isinstance(result[0], MediaIndexerSession)
            assert result[0].label == "Session 1"
            assert result[0].status == "ready"


class TestMediaIndexerClientGetSession:
    """Tests for get_session method."""

    @pytest.mark.asyncio
    async def test_get_session_success(self, client, session_id):
        """Test successful session retrieval."""
        project_id = uuid4()
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "id": str(session_id),
                "project_id": str(project_id),
                "label": "Main Session",
                "status": "ready",
                "duration_seconds": 3600,
            }

            result = await client.get_session(session_id)

            assert result["label"] == "Main Session"
            assert result["duration_seconds"] == 3600


class TestMediaIndexerClientListTemporalIndexes:
    """Tests for list_temporal_indexes method."""

    @pytest.mark.asyncio
    async def test_list_temporal_indexes_success(self, client, session_id):
        """Test successful temporal index listing."""
        temporal_index_id = uuid4()
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = [
                {
                    "id": str(temporal_index_id),
                    "session_id": str(session_id),
                    "status": "completed",
                    "created_at": "2024-01-15T10:00:00Z",
                }
            ]

            result = await client.list_temporal_indexes(session_id)

            assert len(result) == 1
            assert result[0]["status"] == "completed"


class TestMediaIndexerClientListAlignmentRuns:
    """Tests for list_alignment_runs method."""

    @pytest.mark.asyncio
    async def test_list_alignment_runs_success(self, client, session_id):
        """Test successful alignment run listing."""
        alignment_run_id = uuid4()
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = [
                {
                    "id": str(alignment_run_id),
                    "session_id": str(session_id),
                    "status": "completed",
                    "provider": "litellm",
                    "model": "gemini-2.0-flash",
                    "created_at": "2024-01-15T12:00:00Z",
                }
            ]

            result = await client.list_alignment_runs(session_id)

            assert len(result) == 1
            assert result[0]["status"] == "completed"
            assert result[0]["provider"] == "litellm"

    @pytest.mark.asyncio
    async def test_list_alignment_runs_with_status_filter(self, client, session_id):
        """Test alignment run listing with status filter."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = []

            await client.list_alignment_runs(session_id, status="completed")

            # Verify status was passed as query param
            call_args = mock_request.call_args
            assert call_args.kwargs.get("params") == {"status": "completed"}


class TestMediaIndexerClientGetSemanticTimeline:
    """Tests for get_semantic_timeline method."""

    @pytest.mark.asyncio
    async def test_get_semantic_timeline_success(self, client, session_id):
        """Test successful semantic timeline retrieval."""
        temporal_index_id = uuid4()
        note_id = uuid4()

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "provenance": {
                    "session_id": str(session_id),
                },
                "notes": [
                    {
                        "id": str(note_id),
                        "order": 1,
                        "raw": "The combat feels smooth",
                        "alignment_status": "matched",
                        "alignment_subject_id": str(uuid4()),
                        "selected_alignment": {
                            "candidate_alignment_id": str(uuid4()),
                            "retrieval_rank": 1,
                            "start_seconds": 120.0,
                            "end_seconds": 145.0,
                            "confidence": 0.89,
                            "anchors": [
                                {"type": "transcript", "text": "matching text"}
                            ],
                        },
                    },
                    {
                        "id": str(uuid4()),
                        "order": 2,
                        "raw": "Level design is intricate",
                        "alignment_status": "unmatched",
                    },
                ],
            }

            result = await client.get_semantic_timeline(
                session_id=session_id,
                temporal_index_id=temporal_index_id,
            )

            assert isinstance(result, MediaIndexerTimelineSession)
            assert len(result.notes) == 2
            assert result.notes[0].note.raw == "The combat feels smooth"
            assert result.notes[0].alignment is not None
            assert result.notes[0].alignment.start_seconds == 120.0
            assert result.notes[0].alignment.anchors == [
                {"type": "transcript", "text": "matching text"}
            ]
            assert result.notes[1].alignment is None  # unmatched


class TestMediaIndexerClientSearch:
    """Tests for search methods."""

    @pytest.mark.asyncio
    async def test_search_session_success(self, client, session_id):
        """Test successful session search."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "results": [
                    {
                        "session_id": str(session_id),
                        "session_label": "Session 1",
                        "media_filename": "gameplay.mp4",
                        "start_seconds": 120.0,
                        "end_seconds": 145.0,
                        "duration_seconds": 25.0,
                        "score": 0.85,
                        "rank": 1,
                    }
                ]
            }

            result = await client.search_session(
                session_id=session_id,
                query="combat system",
                max_results=10,
            )

            assert len(result) == 1
            assert isinstance(result[0], MediaIndexerSearchResult)
            assert result[0].score == 0.85
            assert result[0].media_filename == "gameplay.mp4"

    @pytest.mark.asyncio
    async def test_search_project_success(self, client, project_id):
        """Test successful project-wide search."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {"results": []}

            result = await client.search_project(
                project_id=project_id,
                query="level design",
                max_results=5,
            )

            assert result == []


class TestMediaIndexerClientErrorHandling:
    """Tests for error handling in _request method."""

    @pytest.mark.asyncio
    async def test_404_raises_not_found(self, client, project_id):
        """Test 404 response raises MediaIndexerNotFoundError."""
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = client_instance

            response = MagicMock()
            response.status_code = 404
            client_instance.request.return_value = response

            with pytest.raises(MediaIndexerNotFoundError):
                await client.get_project(project_id)

    @pytest.mark.asyncio
    async def test_409_raises_conflict(self, client, session_id):
        """Test 409 response raises MediaIndexerConflictError."""
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = client_instance

            response = MagicMock()
            response.status_code = 409
            response.text = "Conflict occurred"
            client_instance.request.return_value = response

            with pytest.raises(MediaIndexerConflictError):
                await client.get_session(session_id)

    @pytest.mark.asyncio
    async def test_500_raises_unavailable(self, client, project_id):
        """Test 500 response raises MediaIndexerUnavailableError."""
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = client_instance

            response = MagicMock()
            response.status_code = 500
            client_instance.request.return_value = response

            with pytest.raises(MediaIndexerUnavailableError):
                await client.get_project(project_id)

    @pytest.mark.asyncio
    async def test_timeout_raises_unavailable(self, client, project_id):
        """Test timeout raises MediaIndexerUnavailableError."""
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = client_instance
            client_instance.request.side_effect = httpx.TimeoutException("Timeout")

            with pytest.raises(MediaIndexerUnavailableError):
                await client.get_project(project_id)

    @pytest.mark.asyncio
    async def test_connect_error_raises_unavailable(self, client, project_id):
        """Test connection error raises MediaIndexerUnavailableError."""
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = client_instance
            client_instance.request.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(MediaIndexerUnavailableError):
                await client.get_project(project_id)

    @pytest.mark.asyncio
    async def test_400_raises_generic_error(self, client, project_id):
        """Test 400 response raises MediaIndexerError."""
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = client_instance

            response = MagicMock()
            response.status_code = 400
            client_instance.request.return_value = response

            with pytest.raises(MediaIndexerError):
                await client.get_project(project_id)
