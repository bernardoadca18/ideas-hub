"""Media Context Provider abstraction.

This module defines the abstraction for retrieving audiovisual context
from the Media Indexer service, with a real implementation and a fake for testing.
"""

from typing import Protocol
from uuid import UUID

from app.schemas.media_indexer import GameAnalysisMediaContext


class MediaContextProvider(Protocol):
    """Protocol for media context retrieval.

    This abstraction allows AnaliseJogosService to remain decoupled
    from the specific Media Indexer client implementation.
    """

    async def get_context(
        self,
        media_project_id: UUID,
        media_session_ids: list[UUID] | None = None,
        max_chars: int = 50000,
    ) -> GameAnalysisMediaContext:
        """Retrieve compact media context for game analysis.

        Args:
            media_project_id: The Media Indexer project ID
            media_session_ids: Optional filter to specific sessions
            max_chars: Maximum characters for the context budget

        Returns:
            GameAnalysisMediaContext with notes, alignments, and search results
        """
        ...


class FakeMediaContextProvider:
    """Fake media context provider for testing.

    Returns empty/neutral context, simulating a scenario where
    Media Indexer is not configured or unavailable.
    """

    async def get_context(
        self,
        media_project_id: UUID,
        media_session_ids: list[UUID] | None = None,
        max_chars: int = 50000,
    ) -> GameAnalysisMediaContext:
        """Return empty context indicating Media Indexer is not available."""
        return GameAnalysisMediaContext(
            project_id=media_project_id,
            sessions=[],
            search_results=[],
            total_notes=0,
            matched_notes=0,
            unmatched_notes=0,
            total_chars=0,
            warnings=["FakeMediaContextProvider: Media Indexer not configured"],
            available=False,
        )
