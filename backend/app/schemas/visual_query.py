"""VisualQuery domain model for structured visual queries in production scripts.

Stage 12: Production Script / Structured Visual Queries

VisualQuery expresses WHAT kind of visual evidence a segment needs,
NOT which exact file/clip to use. Ideas Hub owns the structured query;
Media Indexer (Stage 14) will execute searches against available footage.

Provenance canonicalization:
- LLM provides source_note_id (reference to MediaIndexerTimelineNote)
- Backend validates and fills preferred_session_id, preferred_start_seconds,
  preferred_end_seconds from the trusted GameAnalysisMediaContext
- LLM must NEVER invent timestamps or UUIDs

Backward compatibility:
- visual_queries is optional in BlocoNarrativo
- Old roteiros without visual_queries continue to work
"""

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID, uuid4


class VisualQueryIntent(str, Enum):
    """Intent categories for visual queries."""

    ILLUSTRATION = "illustration"  # General gameplay footage
    EVIDENCE = "evidence"  # Specific moment referenced in narration
    TRANSITION = "transition"  # Bridge between segments
    ATMOSPHERE = "atmosphere"  # Mood/ambiance
    COMPARISON = "comparison"  # Side-by-side or before/after


class VisualQueryImportance(str, Enum):
    """Importance levels for visual queries."""

    REQUIRED = "required"  # Must have this footage
    PREFERRED = "preferred"  # Should have if available
    OPTIONAL = "optional"  # Nice to have


@dataclass
class VisualQuery:
    """Structured visual query for a segment of the production script.

    Attributes:
        id: Unique identifier for this visual query
        order: Order within the block (0-indexed)
        intent: Category of visual need (illustration, evidence, etc.)
        query: Natural language description of what footage is needed
        narration_excerpt: Portion of narration this query relates to
        importance: Priority level (required/preferred/optional)
        source_note_id: ID of the source MediaIndexerTimelineNote (LLM-provided)
        preferred_session_id: Session ID from provenance (backend-filled)
        preferred_start_seconds: Start timestamp from provenance (backend-filled)
        preferred_end_seconds: End timestamp from provenance (backend-filled)
        desired_duration_seconds: Target duration for this footage
        notes: Additional context or constraints
    """

    id: UUID = field(default_factory=uuid4)
    order: int = 0
    intent: str = VisualQueryIntent.ILLUSTRATION.value
    query: str = ""
    narration_excerpt: str | None = None
    importance: str = VisualQueryImportance.PREFERRED.value
    source_note_id: UUID | None = None
    preferred_session_id: UUID | None = None
    preferred_start_seconds: float | None = None
    preferred_end_seconds: float | None = None
    desired_duration_seconds: float | None = None
    notes: str | None = None

    def to_dict(self) -> dict:
        """Serialize VisualQuery to dictionary for JSONB persistence."""
        return {
            "id": str(self.id),
            "order": self.order,
            "intent": self.intent,
            "query": self.query,
            "narration_excerpt": self.narration_excerpt,
            "importance": self.importance,
            "source_note_id": str(self.source_note_id) if self.source_note_id else None,
            "preferred_session_id": str(self.preferred_session_id)
            if self.preferred_session_id
            else None,
            "preferred_start_seconds": self.preferred_start_seconds,
            "preferred_end_seconds": self.preferred_end_seconds,
            "desired_duration_seconds": self.desired_duration_seconds,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VisualQuery":
        """Deserialize VisualQuery from dictionary."""
        return cls(
            id=UUID(data["id"])
            if isinstance(data.get("id"), str)
            else data.get("id", uuid4()),
            order=data.get("order", 0),
            intent=data.get("intent", VisualQueryIntent.ILLUSTRATION.value),
            query=data.get("query", ""),
            narration_excerpt=data.get("narration_excerpt"),
            importance=data.get("importance", VisualQueryImportance.PREFERRED.value),
            source_note_id=UUID(data["source_note_id"])
            if data.get("source_note_id")
            else None,
            preferred_session_id=UUID(data["preferred_session_id"])
            if data.get("preferred_session_id")
            else None,
            preferred_start_seconds=data.get("preferred_start_seconds"),
            preferred_end_seconds=data.get("preferred_end_seconds"),
            desired_duration_seconds=data.get("desired_duration_seconds"),
            notes=data.get("notes"),
        )
