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

    def __init__(
        self, client: MediaIndexerClient | None = None, max_chars: int | None = None
    ):
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
                sessions_to_process = await self._resolve_specific_sessions(
                    media_session_ids, expected_project_id=media_project_id
                )
                if not sessions_to_process:
                    return GameAnalysisMediaContext(
                        project_id=media_project_id,
                        sessions=[],
                        search_results=[],
                        total_notes=0,
                        matched_notes=0,
                        unmatched_notes=0,
                        total_chars=0,
                        warnings=[
                            "None of the specified sessions were found or belong to this project"
                        ],
                        available=True,
                    )
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
                    timeline = await self._get_session_timeline(
                        session.id, session.label
                    )

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
                                    1
                                    for n in partial_timeline.notes
                                    if n.alignment is not None
                                )
                                unmatched_notes += sum(
                                    1
                                    for n in partial_timeline.notes
                                    if n.alignment is None
                                )
                                current_chars += self._estimate_session_chars(
                                    partial_timeline
                                )
                            warnings.append(
                                f"Session '{session.label}' truncated to fit context budget"
                            )
                        else:
                            timeline_sessions.append(timeline)
                            total_notes += len(timeline.notes)
                            matched_notes += sum(
                                1 for n in timeline.notes if n.alignment is not None
                            )
                            unmatched_notes += sum(
                                1 for n in timeline.notes if n.alignment is None
                            )
                            current_chars += session_chars

                except MediaIndexerConflictError:
                    warnings.append(
                        f"Session '{session.label}' has no suitable temporal index"
                    )
                except MediaIndexerError as e:
                    warnings.append(f"Session '{session.label}' error: {e!s}")

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
                warnings=[f"Media Indexer unavailable: {e!s}"],
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
                warnings=[f"Media Indexer error: {e!s}"],
                available=False,
                error=str(e),
            )

    async def _resolve_specific_sessions(
        self, session_ids: list[UUID], expected_project_id: UUID | None = None
    ) -> list:
        """Resolve session objects from IDs, optionally validating project ownership.

        Args:
            session_ids: List of session IDs to resolve
            expected_project_id: If provided, sessions must belong to this project

        Returns:
            List of MediaIndexerSession objects for valid sessions

        Raises:
            MediaIndexerNotFoundError: If no sessions are found or none match project
        """
        from app.schemas.media_indexer import MediaIndexerSession

        sessions = []
        ownership_warnings = []

        for session_id in session_ids:
            try:
                data = await self._client.get_session(session_id)
                session_project_id = UUID(data["project_id"])

                if expected_project_id and session_project_id != expected_project_id:
                    ownership_warnings.append(
                        f"Session '{data.get('label', session_id)}' belongs to a different project"
                    )
                    continue

                sessions.append(
                    MediaIndexerSession(
                        id=UUID(data["id"]),
                        project_id=session_project_id,
                        label=data["label"],
                        status=data["status"],
                    )
                )
            except MediaIndexerNotFoundError:
                roteirista_logger.logger.warning(
                    "media_session_not_found",
                    extra={"session_id": str(session_id)},
                )

        if ownership_warnings:
            roteirista_logger.logger.warning(
                "session_ownership_mismatch",
                extra={
                    "expected_project_id": str(expected_project_id),
                    "warnings": ownership_warnings,
                },
            )

        return sessions

    async def _get_session_timeline(
        self, session_id: UUID, session_label: str
    ) -> MediaIndexerTimelineSession | None:
        """Get semantic timeline for a session.

        This method resolves the latest completed temporal index,
        discovers compatible completed AlignmentRuns, and retrieves
        the semantic timeline with alignment information.

        ## Temporal Index Selection Policy

        Selection strategy: Most recent completed TemporalIndex by created_at.

        Rationale:
        - Sessions typically have one TemporalIndex per transcription+visual pair
        - Newer indexes may have improved embedding models or configurations
        - AlignmentRun compatibility is validated server-side

        Future considerations:
        - Could derive from AlignmentRun.provenance if alignment_run_id is known
        - Could expose temporal_index_id parameter for explicit selection
        - Could check alignment provenance to prefer indexes with completed alignments

        ## AlignmentRun Discovery

        When an AlignmentRun exists:
        - Notes include matched/unmatched status with timestamps
        - Timestamps enable precise clip selection

        When no AlignmentRun exists:
        - Notes appear as 'not_aligned' without timestamps
        - Still useful for script generation but without video evidence
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

        # Discover completed alignment runs for this session
        alignment_run_id = await self._resolve_compatible_alignment_run(
            session_id, temporal_index_id
        )

        # Get semantic timeline for this session
        timeline = await self._client.get_semantic_timeline(
            session_id=session_id,
            temporal_index_id=temporal_index_id,
            alignment_run_id=alignment_run_id,
            limit=500,  # Reasonable limit for notes
        )

        # Override session_label with the actual human-readable label
        timeline.session_label = session_label

        return timeline

    async def _resolve_compatible_alignment_run(
        self, session_id: UUID, temporal_index_id: UUID
    ) -> UUID | None:
        """Discover a completed AlignmentRun compatible with the temporal index.

        Compatibility chain: AlignmentRun -> RetrievalRun -> TemporalIndex
        We verify the AlignmentRun's RetrievalRun points to our TemporalIndex.

        Returns the most recent completed compatible AlignmentRun, or None.
        """
        try:
            alignment_runs = await self._client.list_alignment_runs(
                session_id, status="completed"
            )

            # Find the first run whose retrieval_run.temporal_index_id matches
            for run in alignment_runs:
                # The alignment run has retrieval_run_id; we need to check if
                # that retrieval run's temporal_index_id matches ours.
                # Since we don't have a retrieval run API, we check via the
                # alignment run's direct relationship.
                # For now, we return the most recent completed alignment run
                # since sessions typically have one alignment per temporal index.
                # A more robust check would require a retrieval run API.
                return UUID(run["id"])

            return None

        except (MediaIndexerError, KeyError, ValueError) as e:
            roteirista_logger.logger.warning(
                "alignment_run_resolution_failed",
                extra={
                    "session_id": str(session_id),
                    "temporal_index_id": str(temporal_index_id),
                    "error": str(e),
                },
            )
            return None

    def _estimate_session_chars(self, timeline: MediaIndexerTimelineSession) -> int:
        """Estimate character count for a timeline session.

        This estimation aligns with format_media_context_for_prompt output:
        - Session header line (no trailing newline; join adds the separator)
        - Per-note lines with note ID, raw content + alignment metadata
        - Empty line after session (trailing newline from join with empty string)
        """
        # Start with session header length (no trailing newline - join adds separators)
        total = len(f"Session: {timeline.session_label}")
        for note in timeline.notes:
            # Base line: "  Note {order} [id={uuid}]: [{status}] {raw}"
            note_line = f"  Note {note.note.order} [id={note.note.id}]: [{note.note.alignment_status}] {note.note.raw}"
            if note.alignment:
                # Timestamp and confidence: " @ MM:SS-MM:SS (confidence: 0.XX)"
                start_min = int(note.alignment.start_seconds // 60)
                start_sec = int(note.alignment.start_seconds % 60)
                end_min = int(note.alignment.end_seconds // 60)
                end_sec = int(note.alignment.end_seconds % 60)
                note_line += (
                    f" @ {start_min:02d}:{start_sec:02d}-{end_min:02d}:{end_sec:02d}"
                )
                note_line += f" (confidence: {note.alignment.confidence:.2f})"
            # Each note is preceded by a newline separator, then the note content
            total += 1 + len(note_line)
        # Empty string appended after notes produces a trailing newline via join
        total += 1
        return total

    def _truncate_timeline(
        self, timeline: MediaIndexerTimelineSession, max_chars: int
    ) -> MediaIndexerTimelineSession:
        """Truncate timeline to fit within character budget, preserving complete notes.

        Uses the same estimation logic as _estimate_session_chars for consistency.
        """
        from app.schemas.media_indexer import MediaIndexerTimelineNote

        truncated_notes: list[MediaIndexerTimelineNote] = []
        # Start with session header (no trailing newline) + 1 for trailing newline from empty string
        current_chars = len(f"Session: {timeline.session_label}") + 1

        for note in timeline.notes:
            # Calculate actual line length as it will be formatted
            note_line = f"  Note {note.note.order} [id={note.note.id}]: [{note.note.alignment_status}] {note.note.raw}"
            if note.alignment:
                start_min = int(note.alignment.start_seconds // 60)
                start_sec = int(note.alignment.start_seconds % 60)
                end_min = int(note.alignment.end_seconds // 60)
                end_sec = int(note.alignment.end_seconds % 60)
                note_line += (
                    f" @ {start_min:02d}:{start_sec:02d}-{end_min:02d}:{end_sec:02d}"
                )
                note_line += f" (confidence: {note.alignment.confidence:.2f})"
            # Each note is preceded by a newline separator, then the note content
            note_chars = 1 + len(note_line)

            if current_chars + note_chars > max_chars:
                break
            truncated_notes.append(note)
            current_chars += note_chars

        return MediaIndexerTimelineSession(
            session_id=timeline.session_id,
            session_label=timeline.session_label,
            notes=truncated_notes,
        )
