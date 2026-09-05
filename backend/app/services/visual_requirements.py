"""Host-owned materialization rules for structured script VisualQueries."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.schemas.llm_outputs import LLMVisualQuery
from app.schemas.visual_query import VisualQuery

VISUAL_REQUIREMENTS_POLICY_VERSION = "visual_requirements_v1"
TARGET_VISUAL_BEAT_SECONDS = 30
MAX_VISUAL_QUERIES_PER_SECTION = 5


class VisualRequirementsError(ValueError):
    """A generated visual requirement cannot be safely bound or trusted."""


@dataclass(frozen=True, slots=True)
class VisualQueryCountPolicy:
    minimum: int
    maximum: int


def visual_query_count_policy(duration_seconds: int) -> VisualQueryCountPolicy:
    """Bound visual density without coupling it to sentences or arbitrary block count."""

    if duration_seconds <= 0:
        raise VisualRequirementsError("section duration must be positive")
    minimum = min(
        MAX_VISUAL_QUERIES_PER_SECTION,
        max(1, math.ceil(duration_seconds / TARGET_VISUAL_BEAT_SECONDS)),
    )
    return VisualQueryCountPolicy(
        minimum=minimum,
        maximum=MAX_VISUAL_QUERIES_PER_SECTION,
    )


def materialize_written_visual_queries(
    *,
    generation_run_id: UUID,
    section_key: str,
    duration_seconds: int,
    content: str,
    generated: Iterable[LLMVisualQuery],
    evidence_dossier: dict[str, Any],
) -> list[VisualQuery]:
    """Validate writer output and assign stable identities/provenance for one revision."""

    raw_queries = list(generated)
    count_policy = visual_query_count_policy(duration_seconds)
    if not count_policy.minimum <= len(raw_queries) <= count_policy.maximum:
        raise VisualRequirementsError(
            "section visual query count must be between "
            f"{count_policy.minimum} and {count_policy.maximum}"
        )

    note_provenance = _note_provenance(evidence_dossier)
    cursor = 0
    spans: list[tuple[int, int]] = []
    materialized: list[VisualQuery] = []
    for order, raw in enumerate(raw_queries):
        excerpt = (raw.narration_excerpt or "").strip()
        if not excerpt:
            raise VisualRequirementsError("narration_excerpt is required")
        position = content.find(excerpt, cursor)
        if position < 0:
            raise VisualRequirementsError(
                "narration_excerpt must be a literal, ordered span of section content"
            )
        cursor = position + len(excerpt)
        spans.append((position, cursor))

        preferred_session_id: UUID | None = None
        preferred_start_seconds: float | None = None
        preferred_end_seconds: float | None = None
        if raw.source_note_id is not None:
            provenance = note_provenance.get(raw.source_note_id)
            if provenance is None:
                raise VisualRequirementsError(
                    "source_note_id is not present in trusted media context"
                )
            preferred_session_id = provenance[0]
            preferred_start_seconds = provenance[1]
            preferred_end_seconds = provenance[2]

        materialized.append(
            VisualQuery(
                id=uuid5(
                    NAMESPACE_URL,
                    "neovids:visual-query:"
                    f"{generation_run_id}:{section_key}:{order}",
                ),
                order=order,
                intent=raw.intent.value,
                query=raw.query,
                narration_excerpt=excerpt,
                importance=raw.importance.value,
                source_note_id=raw.source_note_id,
                preferred_session_id=preferred_session_id,
                preferred_start_seconds=preferred_start_seconds,
                preferred_end_seconds=preferred_end_seconds,
                desired_duration_seconds=raw.desired_duration_seconds,
                notes=raw.notes,
            )
        )
    if len(spans) > 1 and (
        spans[0][0] > len(content) * 0.25
        or spans[-1][1] < len(content) * 0.75
    ):
        raise VisualRequirementsError(
            "visual query excerpts must be distributed from section opening to closing"
        )
    return materialized


def validate_preserved_visual_queries(
    *, content: str, queries: Iterable[Any]
) -> None:
    """Keep human edits safe: preserved bindings must still match the edited narration."""

    cursor = 0
    for query in queries:
        excerpt = (getattr(query, "narration_excerpt", None) or "").strip()
        if not excerpt:
            # Historical game-analysis queries were valid before excerpts became
            # mandatory for production-ready faceless scripts. Keep them readable
            # and versionable without fabricating a binding.
            continue
        position = content.find(excerpt, cursor)
        if position < 0:
            raise VisualRequirementsError(
                "human edit changed a VisualQuery narration excerpt; use script "
                "regeneration so visual requirements can be replanned"
            )
        cursor = position + len(excerpt)


def _note_provenance(
    evidence_dossier: dict[str, Any],
) -> dict[UUID, tuple[UUID | None, float | None, float | None]]:
    result: dict[UUID, tuple[UUID | None, float | None, float | None]] = {}
    for fragment in evidence_dossier.get("fragments") or []:
        if not isinstance(fragment, dict) or not fragment.get("media_note_id"):
            continue
        try:
            note_id = UUID(str(fragment["media_note_id"]))
            session_id = (
                UUID(str(fragment["session_id"]))
                if fragment.get("session_id")
                else None
            )
        except (TypeError, ValueError):
            continue
        alignment = fragment.get("alignment")
        start = end = None
        if isinstance(alignment, dict):
            try:
                start = float(alignment["start_seconds"])
                end = float(alignment["end_seconds"])
            except (KeyError, TypeError, ValueError):
                start = end = None
            if start is not None and (start < 0 or end is None or end <= start):
                start = end = None
        result[note_id] = (session_id, start, end)
    return result
