"""Host-owned visual coverage and VisualQuery materialization rules."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.production_profiles import VisualRequirementsPolicy
from app.schemas.visual_query import VisualQuery

VISUAL_REQUIREMENTS_POLICY_VERSION = "visual_requirements_v2"
VISUAL_PRODUCTION_SCRIPT_SCHEMA_VERSION = "2.2"
TARGET_VISUAL_BEAT_SECONDS = 30
MAX_VISUAL_BEATS_PER_LLM_CALL = 5
MAX_VISUAL_BEATS_PER_SECTION = 256  # resource/schema guard, not editorial density
_INTENTS = {"illustration", "evidence", "transition", "atmosphere", "comparison"}
_IMPORTANCES = {"required", "preferred", "optional"}
_BOUNDARY_PATTERN = re.compile(
    r"(?:\n[ \t]*\n+)|(?:[.!?…][\"'”’)]*[ \t\n]+)|(?:[;:][ \t\n]+)|(?:[,—–-][ \t]+)|(?:[ \t\n]+)",
    re.UNICODE,
)


class VisualRequirementsError(ValueError):
    """A visual requirement cannot be safely bound or trusted."""


class UnknownVisualSourceNoteError(VisualRequirementsError):
    """The LLM selected a note UUID outside the trusted dossier."""

    def __init__(self, source_note_id: UUID, *, allowed_count: int) -> None:
        self.source_note_id = source_note_id
        self.allowed_count = allowed_count
        super().__init__(
            f"source_note_id {source_note_id} is not present in trusted media context "
            f"(allowed_count={allowed_count})"
        )


DEFAULT_VISUAL_REQUIREMENTS_POLICY = VisualRequirementsPolicy()


@dataclass(frozen=True, slots=True)
class VisualQueryCountPolicy:
    """Compatibility projection: host-owned beats require exactly this many queries."""

    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class VisualBeat:
    id: UUID
    order: int
    start_char: int
    end_char: int
    text: str
    estimated_duration_seconds: float


@dataclass(frozen=True, slots=True)
class VisualReadinessReport:
    status: str
    policy_version: str
    policy_identity: str
    speakable_content_identity: str
    block_count: int
    visual_beat_count: int
    textual_coverage_ratio: float
    missing_ranges: tuple[dict[str, int], ...]
    overlap_ranges: tuple[dict[str, int], ...]
    issues: tuple[dict[str, Any], ...]
    blocks: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["missing_ranges"] = list(self.missing_ranges)
        value["overlap_ranges"] = list(self.overlap_ranges)
        value["issues"] = list(self.issues)
        value["blocks"] = list(self.blocks)
        return value


def speakable_content_identity(blocks: Iterable[Any]) -> str:
    """Hash narration only; visual enrichment must preserve this identity."""

    contents = [_block_value(block, "conteudo", "") for block in blocks]
    canonical = json.dumps(contents, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def visual_query_count_policy(
    duration_seconds: int,
    policy: VisualRequirementsPolicy = DEFAULT_VISUAL_REQUIREMENTS_POLICY,
) -> VisualQueryCountPolicy:
    """Return semantic beat density without an editorial five-query cap."""

    if duration_seconds <= 0:
        raise VisualRequirementsError("section duration must be positive")
    count = max(1, math.ceil(duration_seconds / policy.target_beat_seconds))
    if count > MAX_VISUAL_BEATS_PER_SECTION:
        raise VisualRequirementsError("section exceeds the bounded visual beat safety limit")
    return VisualQueryCountPolicy(minimum=count, maximum=count)


def segment_visual_beats(
    *,
    section_key: str,
    content: str,
    duration_seconds: int,
    policy: VisualRequirementsPolicy = DEFAULT_VISUAL_REQUIREMENTS_POLICY,
) -> tuple[VisualBeat, ...]:
    """Partition untouched narration into deterministic, contiguous semantic beats."""

    if not content or not content.strip():
        raise VisualRequirementsError("section narration must not be blank")
    desired = visual_query_count_policy(duration_seconds, policy).minimum
    boundaries = _candidate_boundaries(content)
    desired = min(desired, len(boundaries) + 1)
    cuts = _select_cuts(content, boundaries, desired) if desired > 1 else []
    spans = list(zip([0, *cuts], [*cuts, len(content)], strict=True))
    if any(not content[start:end].strip() for start, end in spans):
        raise VisualRequirementsError("visual beat segmentation produced an empty beat")
    content_sha = hashlib.sha256(content.encode()).hexdigest()
    return tuple(
        VisualBeat(
            id=uuid5(
                NAMESPACE_URL,
                "neovids:visual-beat:"
                f"{policy.identity}:{section_key}:{content_sha}:{order}:{start}:{end}",
            ),
            order=order,
            start_char=start,
            end_char=end,
            text=content[start:end],
            estimated_duration_seconds=round(
                duration_seconds * (end - start) / len(content), 6
            ),
        )
        for order, (start, end) in enumerate(spans)
    )


def visual_beat_batches(
    beats: Sequence[VisualBeat],
    policy: VisualRequirementsPolicy = DEFAULT_VISUAL_REQUIREMENTS_POLICY,
) -> tuple[tuple[VisualBeat, ...], ...]:
    size = policy.max_beats_per_llm_call
    return tuple(tuple(beats[index : index + size]) for index in range(0, len(beats), size))


def materialize_written_visual_queries(
    *,
    generation_run_id: UUID,
    section_key: str,
    duration_seconds: int,
    content: str,
    generated: Iterable[Any],
    evidence_dossier: dict[str, Any],
    policy: VisualRequirementsPolicy = DEFAULT_VISUAL_REQUIREMENTS_POLICY,
    beats: Sequence[VisualBeat] | None = None,
) -> list[VisualQuery]:
    """Attach LLM semantics to immutable host-owned beat spans and provenance."""

    host_beats = tuple(beats) if beats is not None else segment_visual_beats(
        section_key=section_key,
        content=content,
        duration_seconds=duration_seconds,
        policy=policy,
    )
    raw_queries = list(generated)
    if len(raw_queries) != len(host_beats):
        raise VisualRequirementsError(
            f"visual enrichment returned {len(raw_queries)} items for "
            f"{len(host_beats)} host-owned beats"
        )
    note_provenance = _note_provenance(evidence_dossier)
    materialized: list[VisualQuery] = []
    for order, (beat, raw) in enumerate(zip(host_beats, raw_queries, strict=True)):
        raw_order = getattr(raw, "beat_order", order)
        if raw_order != beat.order:
            raise VisualRequirementsError("visual beat enrichment order is invalid")
        preferred_session_id: UUID | None = None
        preferred_start_seconds: float | None = None
        preferred_end_seconds: float | None = None
        source_note_id = getattr(raw, "source_note_id", None)
        if source_note_id is not None:
            provenance = note_provenance.get(source_note_id)
            if provenance is None:
                raise UnknownVisualSourceNoteError(
                    source_note_id,
                    allowed_count=len(note_provenance),
                )
            preferred_session_id, preferred_start_seconds, preferred_end_seconds = provenance
        intent = _enum_value(getattr(raw, "intent", None))
        importance = _enum_value(getattr(raw, "importance", None))
        query = str(getattr(raw, "query", "")).strip()
        if intent not in _INTENTS or importance not in _IMPORTANCES or not query:
            raise VisualRequirementsError("visual beat enrichment semantics are invalid")
        materialized.append(
            VisualQuery(
                id=uuid5(NAMESPACE_URL, f"neovids:visual-query:{generation_run_id}:{beat.id}"),
                order=order,
                intent=intent,
                query=query,
                narration_excerpt=beat.text,
                importance=importance,
                source_note_id=source_note_id,
                preferred_session_id=preferred_session_id,
                preferred_start_seconds=preferred_start_seconds,
                preferred_end_seconds=preferred_end_seconds,
                desired_duration_seconds=beat.estimated_duration_seconds,
                notes=getattr(raw, "notes", None),
                visual_beat_id=beat.id,
                coverage_start_char=beat.start_char,
                coverage_end_char=beat.end_char,
                coverage_policy_version=policy.version,
            )
        )
    return materialized


def validate_visual_readiness(
    structure: Any,
    policy: VisualRequirementsPolicy = DEFAULT_VISUAL_REQUIREMENTS_POLICY,
) -> VisualReadinessReport:
    """Canonical production-readiness validator owned by Ideas Hub."""

    blocks = list(_block_value(structure, "blocos", []))
    issues: list[dict[str, Any]] = []
    missing: list[dict[str, int]] = []
    overlaps: list[dict[str, int]] = []
    block_reports: list[dict[str, Any]] = []
    all_query_ids: set[str] = set()
    all_beat_ids: set[str] = set()
    covered_chars = total_chars = total_beats = 0
    for block_order, block in enumerate(blocks):
        content = str(_block_value(block, "conteudo", ""))
        duration = int(_block_value(block, "duracao_segundos", 0))
        expected_beats = segment_visual_beats(
            section_key=f"block-{block_order:03d}",
            content=content,
            duration_seconds=duration,
            policy=policy,
        )
        queries = sorted(
            _block_value(block, "visual_queries", []),
            key=lambda item: int(_block_value(item, "order", 0)),
        )
        total_chars += len(content)
        cursor = 0
        block_covered = 0
        for expected_order, query in enumerate(queries):
            start = _block_value(query, "coverage_start_char", None)
            end = _block_value(query, "coverage_end_char", None)
            excerpt = _block_value(query, "narration_excerpt", None)
            query_id = _block_value(query, "id", None)
            beat_id = _block_value(query, "visual_beat_id", None)
            expected_beat = (
                expected_beats[expected_order]
                if expected_order < len(expected_beats)
                else None
            )
            if query_id is None or str(query_id) in all_query_ids:
                issues.append({"block_order": block_order, "code": "visual_query_id_invalid"})
            else:
                all_query_ids.add(str(query_id))
            if beat_id is None or str(beat_id) in all_beat_ids:
                issues.append({"block_order": block_order, "code": "visual_beat_id_invalid"})
            else:
                all_beat_ids.add(str(beat_id))
            if (
                expected_beat is None
                or start != expected_beat.start_char
                or end != expected_beat.end_char
                or _block_value(query, "coverage_policy_version", None)
                != policy.version
            ):
                issues.append({"block_order": block_order, "code": "visual_beat_plan_mismatch"})
            if int(_block_value(query, "order", -1)) != expected_order:
                issues.append({"block_order": block_order, "code": "visual_query_order_invalid"})
            if not str(_block_value(query, "query", "")).strip():
                issues.append({"block_order": block_order, "code": "visual_query_empty"})
            if _block_value(query, "intent", None) not in _INTENTS:
                issues.append({"block_order": block_order, "code": "visual_query_intent_invalid"})
            if _block_value(query, "importance", None) not in _IMPORTANCES:
                issues.append({"block_order": block_order, "code": "visual_query_importance_invalid"})
            if not isinstance(start, int) or not isinstance(end, int) or end <= start:
                issues.append({"block_order": block_order, "code": "invalid_visual_span"})
                continue
            if start > cursor:
                missing.append({"block_order": block_order, "start_char": cursor, "end_char": start})
            elif start < cursor:
                overlaps.append({"block_order": block_order, "start_char": start, "end_char": cursor})
            if start < 0 or end > len(content) or excerpt != content[start:end]:
                issues.append({"block_order": block_order, "code": "visual_anchor_not_literal"})
            else:
                block_covered += max(0, end - max(start, cursor))
            if _block_value(query, "source_note_id", None) is None and any(
                _block_value(query, field, None) is not None
                for field in ("preferred_session_id", "preferred_start_seconds", "preferred_end_seconds")
            ):
                issues.append({"block_order": block_order, "code": "visual_provenance_invalid"})
            cursor = max(cursor, end)
        if cursor < len(content):
            missing.append({"block_order": block_order, "start_char": cursor, "end_char": len(content)})
        if not queries:
            issues.append({"block_order": block_order, "code": "visual_queries_missing"})
        total_beats += len(queries)
        covered_chars += min(block_covered, len(content))
        block_reports.append(
            {
                "block_order": block_order,
                "character_count": len(content),
                "visual_beat_count": len(queries),
                "covered_character_count": min(block_covered, len(content)),
                "textual_coverage_ratio": round(min(block_covered, len(content)) / len(content), 6)
                if content
                else 1.0,
            }
        )
    coverage = round(covered_chars / total_chars, 6) if total_chars else 1.0
    ready = (not policy.requires_visual_queries_for_final) or (
        bool(blocks) and not issues and not missing and not overlaps and coverage == 1.0
    )
    return VisualReadinessReport(
        status="ready" if ready else "not_ready",
        policy_version=policy.version,
        policy_identity=policy.identity,
        speakable_content_identity=speakable_content_identity(blocks),
        block_count=len(blocks),
        visual_beat_count=total_beats,
        textual_coverage_ratio=coverage,
        missing_ranges=tuple(missing),
        overlap_ranges=tuple(overlaps),
        issues=tuple(issues),
        blocks=tuple(block_reports),
    )


def validate_preserved_visual_queries(*, content: str, queries: Iterable[Any]) -> None:
    """Keep edits safe: host-owned coverage must still match untouched narration."""

    items = list(queries)
    if not items:
        return
    cursor = 0
    for query in sorted(items, key=lambda item: int(_block_value(item, "order", 0))):
        start = _block_value(query, "coverage_start_char", None)
        end = _block_value(query, "coverage_end_char", None)
        excerpt = _block_value(query, "narration_excerpt", None)
        if isinstance(start, int) and isinstance(end, int):
            if start != cursor or end <= start or content[start:end] != excerpt:
                raise VisualRequirementsError(
                    "human edit changed host-owned visual coverage; use visual enrichment to replan requirements"
                )
            cursor = end
            continue
        literal = str(excerpt or "").strip()
        position = content.find(literal, cursor) if literal else cursor
        if literal and position >= 0:
            cursor = position + len(literal)
            continue
        raise VisualRequirementsError(
            "human edit changed a VisualQuery narration excerpt; use script regeneration so visual requirements can be replanned"
        )
    if (
        all(_block_value(item, "coverage_end_char", None) is not None for item in items)
        and cursor != len(content)
    ):
        raise VisualRequirementsError("host-owned visual coverage no longer reaches section end")


def _candidate_boundaries(content: str) -> list[tuple[int, int]]:
    result: dict[int, int] = {}
    for match in _BOUNDARY_PATTERN.finditer(content):
        position = match.end()
        if position <= 0 or position >= len(content):
            continue
        value = match.group(0)
        if "\n\n" in value.replace("\r", ""):
            priority = 0
        elif re.search(r"[.!?…]", value):
            priority = 1
        elif re.search(r"[;:]", value):
            priority = 2
        elif re.search(r"[,—–-]", value):
            priority = 3
        else:
            priority = 4
        result[position] = min(priority, result.get(position, priority))
    for position in range(1, len(content)):
        result.setdefault(position, 5)
    return sorted(result.items())


def _select_cuts(content: str, boundaries: list[tuple[int, int]], count: int) -> list[int]:
    cuts: list[int] = []
    previous = 0
    for order in range(1, count):
        target = round(len(content) * order / count)
        remaining = count - order
        eligible = [
            (position, priority)
            for position, priority in boundaries
            if position > previous and len(content) - position >= remaining
        ]
        if not eligible:
            raise VisualRequirementsError("narration has too few safe visual beat boundaries")
        approximate = len(content) / count
        tolerance = approximate * 0.45
        position, _ = min(
            eligible,
            key=lambda item: (
                0 if abs(item[0] - target) <= tolerance else 1,
                item[1] if abs(item[0] - target) <= tolerance else 5,
                abs(item[0] - target),
                item[0],
            ),
        )
        cuts.append(position)
        previous = position
    return cuts


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else ""


def _block_value(value: Any, key: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _note_provenance(
    evidence_dossier: dict[str, Any],
) -> dict[UUID, tuple[UUID | None, float | None, float | None]]:
    result: dict[UUID, tuple[UUID | None, float | None, float | None]] = {}
    for fragment in evidence_dossier.get("fragments") or []:
        if not isinstance(fragment, dict) or not fragment.get("media_note_id"):
            continue
        try:
            note_id = UUID(str(fragment["media_note_id"]))
            session_id = UUID(str(fragment["session_id"])) if fragment.get("session_id") else None
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
