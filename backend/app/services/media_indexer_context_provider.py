"""Media Indexer context provider implementation.

This module provides the real implementation of MediaContextProvider
that communicates with the Media Indexer service to retrieve audiovisual context.
"""
from uuid import UUID

from app.core.config import settings
from app.core.logging import roteirista_logger
from app.schemas.media_indexer import (
    GameAnalysisMediaContext,
    MediaIndexerTimelineSession,
)
from app.services.media_context_provider import MediaContextProvider
from app.services.media_indexer_client import (
    MediaIndexerClient,
    MediaIndexerConflictError,
    MediaIndexerError,
    MediaIndexerNotFoundError,
    MediaIndexerUnavailableError,
)


class MediaIndexerContextProvider:
    """Real implementation of MediaContextProvider using MediaIndexerClient.

    This provider retrieves semantic timeline data from Media Indexer
    and compacts it into a GameAnalysisMediaContext suitable for
    game analysis workflow.
    """

    def __init__(self, client: MediaIndexerClient | None = None, max_chars: int | None = None):
        self._client = client or MediaIndexerClient()
        self._max_chars = max_chars or settings.game_analysis_media_context_max_chars

    async def get_context(
        self,
        media_project_id: UUID,
        media_session_ids: list[UUID] | None = None,
        max_chars: int | None = None,
    ) -> GameAnalysisMediaContext:
        """Retrieve compact media context for game analysis.

        This method:
        1. Lists sessions in the project (or uses provided session IDs)
        2. For each ready session, retrieves semantic timeline with alignment
        3. Compacts the context to fit within the character budget
        4. Returns a GameAnalysisMediaContext with provenance

        Args:
            media_project_id: The Media Indexer project ID
            media_session_ids: Optional filter to specific sessions
            max_chars: Maximum characters for the context budget

        Returns:
            GameAnalysisMediaContext with notes, alignments, and provenance
        """
        budget = max_chars or self._max_chars

        try:
            # Verify project exists
            await self._client.get_project(media_project_id)

            # Get sessions to process
            if media_session_ids:
                sessions_to_process = await self._resolve_specific_sessions(media_session_ids)
            else:
                sessions_to_process = await self._client.list_sessions(media_project_id)

            # Filter to ready sessions only
            ready_sessions = [s for s in sessions_to_process if s.status == "ready"]

            if not ready_sessions:
                return GameAnalysisMediaContext(
                    project_id=media_project_id,
                    sessions=[],
                    search_results=[],
                    total_notes=0,
                    matched_notes=0,
                    unmatched_notes=0,
                    total_chars=0,
                    warnings=["No ready sessions found in Media Indexer project"],
                    available=True,
                )

            # Collect timeline data for each session
            timeline_sessions: list[MediaIndexerTimelineSession] = []
            total_notes = 0
            matched_notes = 0
            unmatched_notes = 0
            current_chars = 0
            warnings: list[str] = []

            for session in ready_sessions:
                # Stop if we've exceeded the budget
                if current_chars >= budget:
                    warnings.append(
                        f"Context budget exceeded, skipped {len(ready_sessions) - len(timeline_sessions)} session(s)"
                    )
                    break

                try:
                    # Get semantic timeline for this session
                    # Note: This requires a temporal_index_id and optionally alignment_run_id
                    # For now, we use the session's latest temporal index if available
                    timeline = await self._get_session_timeline(session.id)

                    if timeline:
                        # Calculate character contribution
                        session_chars = self._estimate_session_chars(timeline)

                        if current_chars + session_chars > budget:
                            # Try to include partial notes within budget
                            partial_timeline = self._truncate_timeline(
                                timeline, budget - current_chars
                            )
                            if partial_timeline.notes:
                                timeline_sessions.append(partial_timeline)
                                total_notes += len(partial_timeline.notes)
                                matched_notes += sum(
                                    1 for n in partial_timeline.notes if n.alignment is not None
                                )
                                unmatched_notes += sum(
                                    1 for n in partial_timeline.notes if n.alignment is None
                                )
                                current_chars += self._estimate_session_chars(partial_timeline)
                            warnings.append(
                                f"Session '{session.label}' truncated to fit context budget"
                            )
                        else:
                            timeline_sessions.append(timeline)
                            total_notes += len(timeline.notes)
                            matched_notes += sum(
                                1 for n in timeline.notes if n.alignment is not None
                            )
                            unmatched_notes += sum(1 for n in timeline.notes if n.alignment is None)
                            current_chars += session_chars

                except MediaIndexerConflictError:
                    warnings.append(
                        f"Session '{session.label}' has no suitable temporal index"
                    )
                except MediaIndexerError as e:
                    warnings.append(f"Session '{session.label}' error: {str(e)}")

            roteirista_logger.logger.info(
                "media_context_retrieved",
                extra={
                    "project_id": str(media_project_id),
                    "session_count": len(timeline_sessions),
                    "total_notes": total_notes,
                    "matched_notes": matched_notes,
                    "unmatched_notes": unmatched_notes,
                    "total_chars": current_chars,
                },
            )

            return GameAnalysisMediaContext(
                project_id=media_project_id,
                sessions=timeline_sessions,
                search_results=[],
                total_notes=total_notes,
                matched_notes=matched_notes,
                unmatched_notes=unmatched_notes,
                total_chars=current_chars,
                warnings=warnings,
                available=True,
            )

        except MediaIndexerNotFoundError:
            return GameAnalysisMediaContext(
                project_id=media_project_id,
                sessions=[],
                search_results=[],
                total_notes=0,
                matched_notes=0,
                unmatched_notes=0,
                total_chars=0,
                warnings=["Media Indexer project not found"],
                available=False,
                error="Project not found",
            )

        except MediaIndexerUnavailableError as e:
            roteirista_logger.logger.warning(
                "media_indexer_unavailable",
                extra={"project_id": str(media_project_id), "error": str(e)},
            )
            return GameAnalysisMediaContext(
                project_id=media_project_id,
                sessions=[],
                search_results=[],
                total_notes=0,
                matched_notes=0,
                unmatched_notes=0,
                total_chars=0,
                warnings=[f"Media Indexer unavailable: {str(e)}"],
                available=False,
                error=str(e),
            )

        except MediaIndexerError as e:
            roteirista_logger.logger.error(
                "media_indexer_error",
                extra={"project_id": str(media_project_id), "error": str(e)},
            )
            return GameAnalysisMediaContext(
                project_id=media_project_id,
                sessions=[],
                search_results=[],
                total_notes=0,
                matched_notes=0,
                unmatched_notes=0,
                total_chars=0,
                warnings=[f"Media Indexer error: {str(e)}"],
                available=False,
                error=str(e),
            )

    async def _resolve_specific_sessions(
        self, session_ids: list[UUID]
    ) -> list:
        """Resolve session objects from IDs."""
        from app.schemas.media_indexer import MediaIndexerSession

        sessions = []
        for session_id in session_ids:
            try:
                data = await self._client.get_session(session_id)
                sessions.append(
                    MediaIndexerSession(
                        id=UUID(data["id"]),
                        project_id=UUID(data["project_id"]),
                        label=data["label"],
                        status=data["status"],
                    )
                )
            except MediaIndexerNotFoundError:
                roteirista_logger.logger.warning(
                    "media_session_not_found",
                    extra={"session_id": str(session_id)},
                )
        return sessions

    async def _get_session_timeline(
        self, session_id: UUID
    ) -> MediaIndexerTimelineSession | None:
        """Get semantic timeline for a session.

        This method resolves the latest completed temporal index
        and retrieves the semantic timeline with alignment information.
        """
        # Get temporal indexes for the session
        temporal_indexes = await self._client.list_temporal_indexes(session_id)

        # Filter to completed indexes and select the most recent one
        completed_indexes = [
            idx for idx in temporal_indexes if idx.get("status") == "completed"
        ]

        if not completed_indexes:
            return None

        # Sort by created_at descending and take the most recent
        completed_indexes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        latest_index = completed_indexes[0]
        temporal_index_id = UUID(latest_index["id"])

        # Get semantic timeline for this session
        # Note: alignment_run_id is optional - if not provided, notes will be not_aligned
        # In a future enhancement, we could retrieve the latest completed alignment run
        timeline = await self._client.get_semantic_timeline(
            session_id=session_id,
            temporal_index_id=temporal_index_id,
            alignment_run_id=None,  # For now, we don't resolve alignment automatically
            limit=500,  # Reasonable limit for notes
        )

        return timeline

    def _estimate_session_chars(self, timeline: MediaIndexerTimelineSession) -> int:
        """Estimate character count for a timeline session."""
        total = 0
        for note in timeline.notes:
            total += len(note.note.raw)
            if note.alignment:
                total += 200  # Approximate overhead for alignment metadata
        return total

    def _truncate_timeline(
        self, timeline: MediaIndexerTimelineSession, max_chars: int
    ) -> MediaIndexerTimelineSession:
        """Truncate timeline to fit within character budget, preserving complete notes."""
        from app.schemas.media_indexer import MediaIndexerTimelineNote

        truncated_notes: list[MediaIndexerTimelineNote] = []
        current_chars = 0

        for note in timeline.notes:
            note_chars = len(note.note.raw) + (200 if note.alignment else 0)
            if current_chars + note_chars > max_chars:
                break
            truncated_notes.append(note)
            current_chars += note_chars

        return MediaIndexerTimelineSession(
            session_id=timeline.session_id,
            session_label=timeline.session_label,
            notes=truncated_notes,
        )
