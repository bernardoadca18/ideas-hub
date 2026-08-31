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
        "inference",
        "speculation",
        "unverified",
    ]
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)


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
        "inference",
        "speculation",
        "unverified",
    ]
    source_fragment_id: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)


class EvidenceFragmentOutput(BaseModel):
    themes: list[str] = Field(min_length=1, max_length=30)
    claims: list[EvidenceClaimOutput] = Field(default_factory=list, max_length=100)
    open_questions: list[str] = Field(default_factory=list, max_length=30)


class WrittenSectionOutput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)
    transition_out: str | None = Field(default=None, max_length=1000)
    claims_used: list[str] = Field(default_factory=list, max_length=100)
    beats_covered: list[str] = Field(min_length=1, max_length=20)
    visual_intent: str | None = Field(default=None, max_length=5000)
    audio_intent: dict[str, Any] | None = None

    @field_validator("content")
    @classmethod
    def spoken_copy_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("section narration is blank")
        return value


class EditorialCriticIssue(BaseModel):
    section_key: str | None = Field(default=None, max_length=64)
    category: Literal[
        "hook",
        "continuity",
        "redundancy",
        "factuality",
        "evidence",
        "spoken_language",
        "payoff",
    ]
    severity: Literal["warning", "revision_required"]
    actionable_feedback: str = Field(min_length=1, max_length=1000)


class EditorialCriticOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    issues: list[EditorialCriticIssue] = Field(default_factory=list, max_length=100)
    open_loops_closed: bool
    unsupported_claims_detected: bool


class GenerationRunCreate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(protected_namespaces=())

    idempotency_key: str = Field(min_length=8, max_length=128)
    model_strategy: Literal["flash_only", "standard", "hybrid", "strong"] = "standard"


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
