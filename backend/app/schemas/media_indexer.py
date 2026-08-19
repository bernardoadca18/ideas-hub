"""Schemas for Media Indexer client.

These are simplified internal representations of the Media Indexer public API responses,
designed for use in the Ideas Hub domain. They intentionally do not expose all fields
from the external API to maintain clean boundaries.
"""
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class MediaIndexerNote:
    """Simplified note from Media Indexer timeline."""
    id: UUID
    order: int
    raw: str
    alignment_status: str  # matched, unmatched, no_candidates, not_aligned, not_in_alignment_run
    alignment_subject_id: UUID | None = None


@dataclass
class MediaIndexerAlignment:
    """Simplified alignment information for a matched note."""
    candidate_alignment_id: UUID
    retrieval_rank: int
    start_seconds: float
    end_seconds: float
    confidence: float
    reasoning_summary: str | None = None
    timestamp_resolution_seconds: float | None = None


@dataclass
class MediaIndexerSession:
    """Simplified session information from Media Indexer."""
    id: UUID
    project_id: UUID
    label: str
    status: str


@dataclass
class MediaIndexerTimelineNote:
    """A note with optional alignment information from the semantic timeline."""
    note: MediaIndexerNote
    alignment: MediaIndexerAlignment | None = None


@dataclass
class MediaIndexerTimelineSession:
    """Timeline information for a single session."""
    session_id: UUID
    session_label: str
    notes: list[MediaIndexerTimelineNote] = field(default_factory=list)


@dataclass
class MediaIndexerSearchResult:
    """A single media search result."""
    session_id: UUID
    session_label: str
    media_filename: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    score: float
    rank: int
    transcript_preview: str | None = None


@dataclass
class GameAnalysisMediaContext:
    """Compact media context prepared for game analysis workflow.

    This is the internal domain model used by AnaliseJogosService. It contains
    only the information relevant for script generation, transformed from
    external Media Indexer API responses.
    """
    project_id: UUID | None = None
    sessions: list[MediaIndexerTimelineSession] = field(default_factory=list)
    search_results: list[MediaIndexerSearchResult] = field(default_factory=list)
    total_notes: int = 0
    matched_notes: int = 0
    unmatched_notes: int = 0
    total_chars: int = 0
    warnings: list[str] = field(default_factory=list)
    available: bool = False
    error: str | None = None
