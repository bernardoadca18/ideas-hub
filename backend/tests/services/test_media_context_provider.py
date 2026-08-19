"""
Tests for MediaContextProvider implementations.

Tests the abstraction layer and both fake and real implementations.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.media_context_provider import (
    MediaContextProvider,
    FakeMediaContextProvider,
)
from app.services.media_indexer_context_provider import MediaIndexerContextProvider
from app.services.media_indexer_client import (
    MediaIndexerClient,
    MediaIndexerNotFoundError,
    MediaIndexerUnavailableError,
    MediaIndexerConflictError,
    MediaIndexerError,
)
from app.schemas.media_indexer import (
    GameAnalysisMediaContext,
    MediaIndexerSession,
    MediaIndexerTimelineSession,
    MediaIndexerTimelineNote,
    MediaIndexerNote,
    MediaIndexerAlignment,
)


@pytest.fixture
def project_id():
    """Sample project ID."""
    return uuid4()


@pytest.fixture
def session_id():
    """Sample session ID."""
    return uuid4()


@pytest.fixture
def fake_provider():
    """Create a FakeMediaContextProvider instance."""
    return FakeMediaContextProvider()


class TestFakeMediaContextProvider:
    """Tests for FakeMediaContextProvider."""

    @pytest.mark.asyncio
    async def test_returns_empty_context(self, fake_provider, project_id):
        """Test that fake provider returns empty context."""
        result = await fake_provider.get_context(
            media_project_id=project_id,
        )

        assert isinstance(result, GameAnalysisMediaContext)
        assert result.available is False
        assert result.sessions == []
        assert result.total_notes == 0
        assert result.matched_notes == 0
        assert result.unmatched_notes == 0
        assert result.total_chars == 0
        assert len(result.warnings) > 0
        assert "not configured" in result.warnings[0].lower()

    @pytest.mark.asyncio
    async def test_ignores_session_filter(self, fake_provider, project_id, session_id):
        """Test that fake provider ignores session filters."""
        result = await fake_provider.get_context(
            media_project_id=project_id,
            media_session_ids=[session_id],
        )

        assert result.available is False


class TestMediaIndexerContextProvider:
    """Tests for MediaIndexerContextProvider."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock MediaIndexerClient."""
        client = AsyncMock(spec=MediaIndexerClient)
        return client

    @pytest.fixture
    def provider(self, mock_client):
        """Create a MediaIndexerContextProvider with mock client."""
        return MediaIndexerContextProvider(client=mock_client, max_chars=50000)

    def _make_session(self, session_id, status="ready"):
        """Create a mock MediaIndexerSession."""
        return MediaIndexerSession(
            id=session_id,
            project_id=uuid4(),
            label=f"Session {session_id}",
            status=status,
        )

    def _make_timeline(self, session_id, num_notes=2):
        """Create a MediaIndexerTimelineSession with notes."""
        notes = []
        for i in range(num_notes):
            note = MediaIndexerNote(
                id=uuid4(),
                order=i,
                raw=f"Test note {i} " * 5,
                alignment_status="matched" if i % 2 == 0 else "unmatched",
            )
            alignment = None
            if i % 2 == 0:
                alignment = MediaIndexerAlignment(
                    candidate_alignment_id=uuid4(),
                    retrieval_rank=1,
                    start_seconds=float(i * 60),
                    end_seconds=float(i * 60 + 30),
                    confidence=0.85,
                )
            notes.append(MediaIndexerTimelineNote(note=note, alignment=alignment))

        return MediaIndexerTimelineSession(
            session_id=session_id,
            session_label=f"Session {session_id}",
            notes=notes,
        )

    @pytest.mark.asyncio
    async def test_get_context_success(self, provider, mock_client, project_id, session_id):
        """Test successful context retrieval."""
        session = self._make_session(session_id)
        timeline = self._make_timeline(session_id, num_notes=3)

        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.list_sessions.return_value = [session]
        mock_client.list_temporal_indexes.return_value = [
            {"id": str(uuid4()), "status": "completed", "created_at": "2024-01-15T10:00:00Z"}
        ]
        mock_client.get_semantic_timeline.return_value = timeline

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is True
        assert result.total_notes == 3
        assert result.matched_notes == 2  # notes 0 and 2 are matched
        assert result.unmatched_notes == 1  # note 1
        assert len(result.sessions) == 1
        mock_client.get_project.assert_called_once_with(project_id)
        mock_client.list_sessions.assert_called_once_with(project_id)
        mock_client.get_semantic_timeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_context_filters_sessions(
        self, provider, mock_client, project_id, session_id
    ):
        """Test that session filters are applied."""
        other_session_id = uuid4()
        session1 = self._make_session(session_id)
        session2 = self._make_session(other_session_id)

        # When using media_session_ids, sessions are resolved individually
        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.get_session.return_value = {
            "id": str(session_id),
            "project_id": str(project_id),
            "label": "Session 1",
            "status": "ready",
        }
        timeline = self._make_timeline(session_id, num_notes=1)
        mock_client.list_temporal_indexes.return_value = [
            {"id": str(uuid4()), "status": "completed", "created_at": "2024-01-15T10:00:00Z"}
        ]
        mock_client.get_semantic_timeline.return_value = timeline

        result = await provider.get_context(
            media_project_id=project_id,
            media_session_ids=[session_id],
            max_chars=50000,
        )

        assert result.available is True
        # Should have called get_session for the specific session_id, not list_sessions
        mock_client.get_session.assert_called_once_with(session_id)
        mock_client.list_sessions.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_context_project_not_found(self, provider, mock_client, project_id):
        """Test handling of project not found."""
        mock_client.get_project.side_effect = MediaIndexerNotFoundError("Not found")

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is False
        assert any("not found" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_get_context_no_sessions(self, provider, mock_client, project_id):
        """Test handling when project has no sessions."""
        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.list_sessions.return_value = []

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is True
        assert result.total_notes == 0
        assert any("no ready sessions" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_get_context_no_completed_temporal_index(
        self, provider, mock_client, project_id, session_id
    ):
        """Test handling when session has no completed temporal index."""
        session = self._make_session(session_id)
        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.list_sessions.return_value = [session]
        mock_client.list_temporal_indexes.return_value = []  # No temporal indexes

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is True
        assert result.total_notes == 0
        # No timeline was retrieved, so no sessions in result
        assert len(result.sessions) == 0

    @pytest.mark.asyncio
    async def test_get_context_truncates_large_timeline(
        self, provider, mock_client, project_id, session_id
    ):
        """Test that large timelines are truncated to respect max_chars."""
        session = self._make_session(session_id)

        # Create a large timeline with many notes
        notes = []
        for i in range(100):
            note = MediaIndexerNote(
                id=uuid4(),
                order=i,
                raw="A" * 50,  # 50 chars each
                alignment_status="matched",
            )
            alignment = MediaIndexerAlignment(
                candidate_alignment_id=uuid4(),
                retrieval_rank=1,
                start_seconds=float(i * 60),
                end_seconds=float(i * 60 + 30),
                confidence=0.85,
            )
            notes.append(MediaIndexerTimelineNote(note=note, alignment=alignment))

        timeline = MediaIndexerTimelineSession(
            session_id=session_id,
            session_label="Large Session",
            notes=notes,
        )

        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.list_sessions.return_value = [session]
        mock_client.list_temporal_indexes.return_value = [
            {"id": str(uuid4()), "status": "completed", "created_at": "2024-01-15T10:00:00Z"}
        ]
        mock_client.get_semantic_timeline.return_value = timeline

        # Use small budget — each note is 50 chars + 200 alignment overhead = 250 chars
        # Budget of 500 should only fit 2 notes
        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=500,
        )

        assert result.available is True
        assert len(result.sessions) == 1
        # Should have truncated notes, not all 100
        assert len(result.sessions[0].notes) < 100
        assert any("truncat" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_get_context_fail_open_on_unavailable(
        self, provider, mock_client, project_id
    ):
        """Test that provider fails open when Media Indexer is unavailable."""
        mock_client.get_project.side_effect = MediaIndexerUnavailableError("Connection refused")

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is False
        assert len(result.warnings) > 0
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_get_context_skip_non_ready_sessions(
        self, provider, mock_client, project_id, session_id
    ):
        """Test that non-ready sessions are skipped."""
        ready_session = self._make_session(session_id, status="ready")
        processing_session = self._make_session(uuid4(), status="processing")

        timeline = self._make_timeline(session_id, num_notes=1)
        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.list_sessions.return_value = [ready_session, processing_session]
        mock_client.list_temporal_indexes.return_value = [
            {"id": str(uuid4()), "status": "completed", "created_at": "2024-01-15T10:00:00Z"}
        ]
        mock_client.list_alignment_runs.return_value = []
        mock_client.get_semantic_timeline.return_value = timeline

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is True
        # Only the ready session should be processed
        assert len(result.sessions) == 1
        assert result.total_notes == 1

    @pytest.mark.asyncio
    async def test_get_context_discovers_alignment_run(
        self, provider, mock_client, project_id, session_id
    ):
        """Test that completed alignment runs are discovered and used."""
        session = self._make_session(session_id)
        alignment_run_id = uuid4()

        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.list_sessions.return_value = [session]
        mock_client.list_temporal_indexes.return_value = [
            {"id": str(uuid4()), "status": "completed", "created_at": "2024-01-15T10:00:00Z"}
        ]
        mock_client.list_alignment_runs.return_value = [
            {"id": str(alignment_run_id), "status": "completed"}
        ]

        # Create timeline with matched note
        note = MediaIndexerNote(
            id=uuid4(),
            order=0,
            raw="Matched note with timestamp",
            alignment_status="matched",
        )
        alignment = MediaIndexerAlignment(
            candidate_alignment_id=uuid4(),
            retrieval_rank=1,
            start_seconds=120.0,
            end_seconds=180.0,
            confidence=0.95,
            anchors=[{"type": "transcript", "text": "evidence"}],
        )
        timeline = MediaIndexerTimelineSession(
            session_id=session_id,
            session_label="Test Session",
            notes=[MediaIndexerTimelineNote(note=note, alignment=alignment)],
        )
        mock_client.get_semantic_timeline.return_value = timeline

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is True
        assert result.matched_notes == 1
        # Verify alignment run was discovered
        mock_client.list_alignment_runs.assert_called_once_with(
            session_id, status="completed"
        )
        # Verify alignment_run_id was passed to semantic timeline
        call_kwargs = mock_client.get_semantic_timeline.call_args.kwargs
        assert call_kwargs["alignment_run_id"] == alignment_run_id

    @pytest.mark.asyncio
    async def test_get_context_validates_session_ownership(
        self, provider, mock_client, project_id, session_id
    ):
        """Test that sessions from different projects are rejected."""
        other_project_id = uuid4()

        mock_client.get_session.return_value = {
            "id": str(session_id),
            "project_id": str(other_project_id),  # Different project
            "label": "Wrong Project Session",
            "status": "ready",
        }

        result = await provider.get_context(
            media_project_id=project_id,
            media_session_ids=[session_id],
            max_chars=50000,
        )

        # Should return empty with warning that no sessions matched
        assert result.available is True
        assert result.total_notes == 0
        assert any("were found or belong" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_get_context_preserves_anchors(
        self, provider, mock_client, project_id, session_id
    ):
        """Test that alignment anchors are preserved in the context."""
        session = self._make_session(session_id)

        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.list_sessions.return_value = [session]
        mock_client.list_temporal_indexes.return_value = [
            {"id": str(uuid4()), "status": "completed", "created_at": "2024-01-15T10:00:00Z"}
        ]
        mock_client.list_alignment_runs.return_value = []

        # Create timeline with anchors
        note = MediaIndexerNote(
            id=uuid4(),
            order=0,
            raw="Note with anchors",
            alignment_status="matched",
        )
        anchors = [
            {"type": "transcript", "text": "matching evidence", "timestamp": 125.5},
            {"type": "visual", "frame": 4500, "confidence": 0.9},
        ]
        alignment = MediaIndexerAlignment(
            candidate_alignment_id=uuid4(),
            retrieval_rank=1,
            start_seconds=120.0,
            end_seconds=180.0,
            confidence=0.95,
            anchors=anchors,
        )
        timeline = MediaIndexerTimelineSession(
            session_id=session_id,
            session_label="Test Session",
            notes=[MediaIndexerTimelineNote(note=note, alignment=alignment)],
        )
        mock_client.get_semantic_timeline.return_value = timeline

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is True
        assert len(result.sessions) == 1
        assert result.sessions[0].notes[0].alignment.anchors == anchors

    @pytest.mark.asyncio
    async def test_get_context_uses_real_session_label(
        self, provider, mock_client, project_id, session_id
    ):
        """Test that human-readable session label is used instead of UUID."""
        session = MediaIndexerSession(
            id=session_id,
            project_id=project_id,
            label="Main Gameplay Session - Dark Souls",
            status="ready",
        )

        mock_client.get_project.return_value = {"id": str(project_id), "name": "Test"}
        mock_client.list_sessions.return_value = [session]
        mock_client.list_temporal_indexes.return_value = [
            {"id": str(uuid4()), "status": "completed", "created_at": "2024-01-15T10:00:00Z"}
        ]
        mock_client.list_alignment_runs.return_value = []

        timeline = self._make_timeline(session_id, num_notes=1)
        mock_client.get_semantic_timeline.return_value = timeline

        result = await provider.get_context(
            media_project_id=project_id,
            max_chars=50000,
        )

        assert result.available is True
        assert result.sessions[0].session_label == "Main Gameplay Session - Dark Souls"
