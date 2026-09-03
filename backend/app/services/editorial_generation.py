"""Deterministic duration intent, generation strategy and section budgeting."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from app.core.config import Settings, settings
from app.production_profiles import ProductionProfile

DURATION_INTENT_VERSION = "duration_intent_v1"
GENERATION_STRATEGY_VERSION = "editorial_generation_strategy_v2"
SECTION_PLAN_VERSION = "editorial_section_plan_v1"
CONTENT_CAPACITY_VERSION = "content_capacity_estimate_v1"


class DurationMode(StrEnum):
    EXPLICIT_TARGET = "explicit_target"
    PROFILE_DEFAULT = "profile_default"
    CONTENT_DRIVEN = "content_driven"


class DurationTargetSource(StrEnum):
    USER = "user"
    PROFILE = "profile"
    CONTENT = "content"
    HISTORICAL = "historical_unresolved"


class GenerationStrategy(StrEnum):
    SINGLE_PASS = "single_pass"
    STAGED = "staged"
    HIERARCHICAL_LONG_FORM = "hierarchical_long_form"


@dataclass(frozen=True)
class ContentCapacityEstimate:
    estimated_seconds: int
    confidence: str
    evidence_units: int
    limiting_reason: str | None
    version: str = CONTENT_CAPACITY_VERSION

    @property
    def identity(self) -> str:
        return _identity(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "identity": self.identity,
        }


@dataclass(frozen=True)
class ResolvedDurationIntent:
    mode: DurationMode
    source: DurationTargetSource
    target_seconds: int | None
    profile_id: str
    version: str = DURATION_INTENT_VERSION

    @property
    def identity(self) -> str:
        return _identity(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "mode": self.mode.value,
            "source": self.source.value,
            "identity": self.identity,
        }


@dataclass(frozen=True)
class SectionBudget:
    key: str
    order: int
    chapter_order: int
    target_duration_seconds: int | None
    target_words: int | None
    min_words: int | None
    max_words: int | None


@dataclass(frozen=True)
class GenerationPlan:
    strategy: GenerationStrategy
    strategy_version: str
    duration_intent: ResolvedDurationIntent
    target_words: int | None
    chapter_count: int
    sections: tuple[SectionBudget, ...]
    max_calls: int
    identity: str


def _identity(payload: Any) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def resolve_duration_intent(
    *,
    mode: DurationMode | str | None,
    requested_target_seconds: int | None,
    profile: ProductionProfile,
) -> ResolvedDurationIntent:
    resolved_mode = DurationMode(mode or DurationMode.PROFILE_DEFAULT)
    target: int | None
    if resolved_mode is DurationMode.EXPLICIT_TARGET:
        if requested_target_seconds is None:
            raise ValueError("explicit_target requires target_duration_seconds")
        target = requested_target_seconds
        if target > profile.max_practical_duration_seconds:
            raise ValueError(
                f"target exceeds the {profile.id} practical maximum "
                f"({profile.max_practical_duration_seconds}s)"
            )
        source = DurationTargetSource.USER
    elif resolved_mode is DurationMode.PROFILE_DEFAULT:
        target = profile.duracao.default_target_seconds
        if target is None:
            raise ValueError(
                f"profile {profile.id} has no default target; choose explicit_target or content_driven"
            )
        if requested_target_seconds is not None and requested_target_seconds != target:
            raise ValueError(
                "profile_default cannot carry an unrelated explicit target"
            )
        source = DurationTargetSource.PROFILE
    else:
        if not profile.duracao.content_driven_allowed:
            raise ValueError(
                f"profile {profile.id} does not allow content-driven duration"
            )
        if requested_target_seconds is not None:
            raise ValueError("content_driven must not carry target_duration_seconds")
        target = None
        source = DurationTargetSource.CONTENT
    return ResolvedDurationIntent(
        mode=resolved_mode,
        source=source,
        target_seconds=target,
        profile_id=profile.id,
    )


def select_generation_strategy(
    intent: ResolvedDurationIntent,
    *,
    evidence_chars: int = 0,
    evidence_units: int = 0,
    config: Settings = settings,
) -> GenerationStrategy:
    target = intent.target_seconds
    if target is None:
        capacity = estimate_content_capacity(
            evidence_chars=evidence_chars, evidence_units=evidence_units
        )
        estimated = capacity.estimated_seconds
        if estimated <= config.generation_single_pass_max_seconds:
            return GenerationStrategy.SINGLE_PASS
        if estimated <= config.generation_staged_max_seconds:
            return GenerationStrategy.STAGED
        return GenerationStrategy.HIERARCHICAL_LONG_FORM
    if target <= config.generation_single_pass_max_seconds:
        return GenerationStrategy.SINGLE_PASS
    if target <= config.generation_staged_max_seconds:
        return GenerationStrategy.STAGED
    return GenerationStrategy.HIERARCHICAL_LONG_FORM


def estimate_content_capacity(
    *,
    evidence_chars: int = 0,
    evidence_units: int = 0,
    words_per_minute: float = 145.0,
) -> ContentCapacityEstimate:
    words_from_chars = max(0, evidence_chars) / 10
    words_from_units = max(0, evidence_units) * 120
    estimated_words = max(words_from_chars, words_from_units)
    estimated_seconds = round(estimated_words * 60 / words_per_minute)
    units = max(1, evidence_units, evidence_chars // 1000)
    if estimated_seconds < 600:
        confidence = "low"
        limiting_reason = "insufficient_evidence"
    elif estimated_seconds < 1800:
        confidence = "medium"
        limiting_reason = None
    else:
        confidence = "high"
        limiting_reason = None
    return ContentCapacityEstimate(
        estimated_seconds=estimated_seconds,
        confidence=confidence,
        evidence_units=units,
        limiting_reason=limiting_reason,
    )


def build_generation_plan(
    *,
    intent: ResolvedDurationIntent,
    words_per_minute: float,
    evidence_chars: int = 0,
    evidence_units: int = 0,
    config: Settings = settings,
) -> GenerationPlan:
    strategy = select_generation_strategy(
        intent,
        evidence_chars=evidence_chars,
        evidence_units=evidence_units,
        config=config,
    )
    target = intent.target_seconds
    target_words = round(words_per_minute * target / 60) if target else None
    if target is None:
        capacity = estimate_content_capacity(
            evidence_chars=evidence_chars, evidence_units=evidence_units
        )
        effective_seconds = capacity.estimated_seconds
        section_count = max(
            1,
            min(
                config.generation_max_sections,
                math.ceil(effective_seconds / config.generation_section_target_seconds),
            ),
        )
        chapter_count = max(1, math.ceil(section_count / 6))
    else:
        section_count = max(
            1, math.ceil(target / config.generation_section_target_seconds)
        )
        chapter_count = max(
            1, math.ceil(target / config.generation_chapter_target_seconds)
        )
    if section_count > config.generation_max_sections:
        raise ValueError("generation would exceed configured section budget")
    section_seconds = _distribute(target, section_count)
    section_words = _distribute(target_words, section_count)
    sections: list[SectionBudget] = []
    for index in range(section_count):
        words = section_words[index]
        sections.append(
            SectionBudget(
                key=f"section-{index + 1:03d}",
                order=index,
                chapter_order=min(
                    chapter_count - 1, index * chapter_count // section_count
                ),
                target_duration_seconds=section_seconds[index],
                target_words=words,
                min_words=round(words * 0.85) if words is not None else None,
                max_words=round(words * 1.15) if words is not None else None,
            )
        )
    payload = {
        "strategy": strategy.value,
        "strategy_version": GENERATION_STRATEGY_VERSION,
        "duration_intent": intent.to_dict(),
        "target_words": target_words,
        "chapter_count": chapter_count,
        "sections": [asdict(item) for item in sections],
        "max_calls": config.generation_max_calls,
    }
    return GenerationPlan(
        strategy=strategy,
        strategy_version=GENERATION_STRATEGY_VERSION,
        duration_intent=intent,
        target_words=target_words,
        chapter_count=chapter_count,
        sections=tuple(sections),
        max_calls=config.generation_max_calls,
        identity=_identity(payload),
    )


def validate_section_words(actual_words: int, budget: SectionBudget) -> dict[str, Any]:
    if budget.target_words is None:
        status = "estimate_only"
    elif actual_words < (budget.min_words or 0) * 0.7:
        status = "severely_under_budget"
    elif actual_words < (budget.min_words or 0):
        status = "under_budget"
    elif actual_words > (budget.max_words or actual_words) * 1.3:
        status = "severely_over_budget"
    elif actual_words > (budget.max_words or actual_words):
        status = "over_budget"
    else:
        status = "within_budget"
    return {
        "version": SECTION_PLAN_VERSION,
        "section_key": budget.key,
        "actual_words": actual_words,
        "target_words": budget.target_words,
        "word_deficit": max(0, budget.target_words - actual_words)
        if budget.target_words is not None
        else None,
        "word_surplus": max(0, actual_words - budget.target_words)
        if budget.target_words is not None
        else None,
        "min_words": budget.min_words,
        "max_words": budget.max_words,
        "status": status,
        "revision_required": status
        in {
            "severely_under_budget",
            "under_budget",
            "severely_over_budget",
            "over_budget",
        },
    }


def content_capacity_report(
    *,
    evidence_claims: int,
    evidence_chars: int,
    target_words: int | None,
    trusted_evidence_claims: int | None = None,
) -> dict[str, Any]:
    trusted = (
        evidence_claims
        if trusted_evidence_claims is None
        else max(0, min(evidence_claims, trusted_evidence_claims))
    )
    # Snippet volume is only a weak floor. Canonical claims, weighted by trust,
    # determine whether factual depth is actually available.
    claim_capacity = evidence_claims * 70 + trusted * 90
    capacity_words = max(claim_capacity, round(evidence_chars / 20))
    ratio = capacity_words / target_words if target_words else None
    return {
        "version": "content_capacity_v1",
        "evidence_claims": evidence_claims,
        "evidence_chars": evidence_chars,
        "trusted_evidence_claims": trusted,
        "estimated_supported_words": capacity_words,
        "target_words": target_words,
        "ratio": round(ratio, 4) if ratio is not None else None,
        "status": "probably_insufficient"
        if ratio is not None and ratio < 0.55
        else "plausible",
        "advisory_only": True,
    }


def _distribute(total: int | None, count: int) -> list[int | None]:
    if total is None:
        return [None] * count
    quotient, remainder = divmod(total, count)
    return [quotient + (1 if index < remainder else 0) for index in range(count)]
