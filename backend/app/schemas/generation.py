"""Strict contracts for staged editorial planning and section writing."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.analise_jogo import AnaliseJogoRequest
from app.services.editorial_generation import DurationMode


class PlannedSectionOutput(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1000)
    narrative_role: str = Field(min_length=1, max_length=100)
    beats: list[str] = Field(min_length=1, max_length=12)
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)
    claim_refs: list[str] = Field(default_factory=list, max_length=50)
    must_cover: list[str] = Field(min_length=1, max_length=20)
    must_not_repeat: list[str] = Field(default_factory=list, max_length=20)
    transition_target: str | None = Field(default=None, max_length=500)


class PlannedClaimOutput(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1000)
    evidence_tier: Literal[
        "gameplay_note",
        "author_opinion",
        "official_confirmed",
        "official_observation",
        "reliable_secondary",
        "leak_authenticated",
        "inference",
        "speculation",
        "unverified",
    ]
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)
    source_trust: Literal[
        "primary_official",
        "reliable_secondary",
        "community",
        "unverified",
        "human_author",
        "gameplay_evidence",
    ] = "unverified"
    claim_status: Literal[
        "confirmed",
        "official_observation",
        "reported",
        "strongly_supported",
        "interpretation",
        "inference",
        "rumor",
        "leak",
        "speculation",
        "unknown",
        "author_opinion",
        "gameplay_observation",
    ] = "unknown"
    qualification: str | None = Field(default=None, max_length=1000)
    support_scope: str | None = Field(default=None, max_length=1000)
    contradicting_source_refs: list[str] = Field(default_factory=list, max_length=20)
    legacy_evidence_tier: str | None = Field(default=None, max_length=64)


class PlannedChapterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1000)


class GlobalEditorialPlanOutput(BaseModel):
    """Small global enrichment; Python remains owner of the plan envelope."""

    model_config = ConfigDict(extra="forbid")

    thesis: str = Field(min_length=1, max_length=2000)
    audience_promise: str = Field(min_length=1, max_length=1000)
    chapters: list[PlannedChapterOutput] = Field(min_length=1, max_length=30)
    open_loops: list[str] = Field(default_factory=list, max_length=30)


class PlannedSectionBatchOutput(BaseModel):
    """Bounded editorial enrichment for host-selected section keys."""

    model_config = ConfigDict(extra="forbid")

    sections: list[PlannedSectionOutput] = Field(min_length=1, max_length=4)


class EditorialPlanOutput(BaseModel):
    thesis: str = Field(min_length=1, max_length=2000)
    audience_promise: str = Field(min_length=1, max_length=1000)
    chapters: list[str] = Field(min_length=1, max_length=30)
    sections: list[PlannedSectionOutput] = Field(min_length=1, max_length=120)
    claim_ledger: list[PlannedClaimOutput] = Field(default_factory=list, max_length=500)
    open_loops: list[str] = Field(default_factory=list, max_length=30)


class EvidenceClaimOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)
    evidence_tier: Literal[
        "gameplay_note",
        "author_opinion",
        "official_confirmed",
        "official_observation",
        "reliable_secondary",
        "leak_authenticated",
        "inference",
        "speculation",
        "unverified",
    ]
    source_fragment_id: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)


class ExternalClaimOutput(BaseModel):
    """One source-local claim. IDs and trust remain host-owned."""

    model_config = ConfigDict(extra="forbid")

    source_fragment_id: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=400)
    claim_status: Literal[
        "confirmed",
        "official_observation",
        "reported",
        "strongly_supported",
        "interpretation",
        "inference",
        "rumor",
        "leak",
        "speculation",
        "unknown",
    ]
    confidence: float = Field(ge=0, le=1)
    qualification: str | None = Field(default=None, max_length=300)
    support_scope: str | None = Field(default=None, max_length=300)
    contradiction_note: str | None = Field(default=None, max_length=300)


class ExternalClaimExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ExternalClaimOutput] = Field(default_factory=list, max_length=4)


class EvidenceFragmentOutput(BaseModel):
    themes: list[str] = Field(min_length=1, max_length=30)
    claims: list[EvidenceClaimOutput] = Field(default_factory=list, max_length=100)
    open_questions: list[str] = Field(default_factory=list, max_length=30)


class WrittenSectionOutput(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)

    @field_validator("content")
    @classmethod
    def spoken_copy_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("section narration is blank")
        return value


class EditorialCriticIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_key: str | None = Field(default=None, max_length=64)
    category: Literal[
        "hook",
        "continuity",
        "redundancy",
        "factuality",
        "evidence",
        "spoken_language",
        "payoff",
        "unsupported_specificity",
        "unsupported_claim",
        "overstated_claim",
        "uncertainty_lost",
        "source_mismatch",
        "must_cover",
        "must_not_repeat",
        "ai_prose",
        "fake_hype",
    ]
    severity: Literal["warning", "revision_required", "blocking"]
    actionable_feedback: str = Field(min_length=1, max_length=1000)
    claim_ref: str | None = Field(default=None, max_length=100)
    excerpt: str | None = Field(default=None, max_length=500)


class EditorialCriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    issues: list[EditorialCriticIssue] = Field(default_factory=list, max_length=100)
    open_loops_closed: bool
    unsupported_claims_detected: bool


class ClaimLanguageAssessment(BaseModel):
    """Auditable semantic judgment for one claim actually used in prose."""

    model_config = ConfigDict(extra="forbid")

    claim_ref: str = Field(min_length=1, max_length=100)
    language_proportional: bool
    attribution_present: bool
    qualification_present: bool
    scope_preserved: bool


class SectionEditorialAuditOutput(BaseModel):
    """Post-write observations; planning metadata cannot self-certify prose."""

    model_config = ConfigDict(extra="forbid")

    revision_required: bool
    issues: list[EditorialCriticIssue] = Field(default_factory=list, max_length=50)
    actual_claim_refs: list[str] = Field(default_factory=list, max_length=50)
    actual_beats_covered: list[str] = Field(default_factory=list, max_length=20)
    actual_summary: str = Field(min_length=1, max_length=1500)
    opened_loops: list[str] = Field(default_factory=list, max_length=20)
    closed_loops: list[str] = Field(default_factory=list, max_length=20)
    claim_language_assessments: list[ClaimLanguageAssessment] = Field(
        default_factory=list, max_length=50
    )


class GenerationRunCreate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(protected_namespaces=())

    idempotency_key: str = Field(min_length=8, max_length=128)
    model_strategy: Literal["flash_only", "standard", "hybrid", "strong"] = "standard"


class RevisionGenerationRunCreate(GenerationRunCreate):
    feedback: str = Field(min_length=1, max_length=10_000)

    @field_validator("feedback")
    @classmethod
    def non_blank_feedback(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("feedback must not be blank")
        return value


class GameGenerationRunCreate(AnaliseJogoRequest):
    model_config: ClassVar[ConfigDict] = ConfigDict(protected_namespaces=())

    idempotency_key: str = Field(min_length=8, max_length=128)
    model_strategy: Literal["flash_only", "standard", "hybrid", "strong"] = "standard"


class GenerationPreviewRequest(BaseModel):
    production_profile: str
    duration_mode: DurationMode
    target_duration_seconds: int | None = Field(default=None, ge=60, le=28_800)
    evidence_chars: int = Field(default=0, ge=0, le=2_000_000)


class GenerationRunResponse(BaseModel):
    id: UUID
    ideia_id: UUID
    roteiro_id: UUID | None
    parent_roteiro_id: UUID | None
    generation_intent: str
    revision_feedback: str | None
    status: str
    phase: str
    generation_strategy: str
    production_profile: str
    duration_mode: str
    duration_target_source: str
    target_duration_seconds: int | None
    target_words: int | None
    total_sections: int
    completed_sections: int
    plan: dict[str, Any]
    call_usage: dict[str, Any]
    error_category: str | None
    error_message: str | None
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True
