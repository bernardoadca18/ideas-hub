"""Validated persistence and revision contracts for production scripts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PersistedVisualQuery(BaseModel):
    """Backward-compatible persisted VisualQuery, including trusted provenance."""

    model_config = ConfigDict(extra="allow")

    id: UUID | None = None
    order: int = Field(default=0, ge=0)
    intent: str = Field(default="illustration", min_length=1)
    query: str = ""
    narration_excerpt: str | None = None
    importance: str = "preferred"
    source_note_id: UUID | None = None
    preferred_session_id: UUID | None = None
    preferred_start_seconds: float | None = Field(default=None, ge=0)
    preferred_end_seconds: float | None = Field(default=None, ge=0)
    desired_duration_seconds: float | None = Field(default=None, gt=0)
    notes: str | None = None

    def model_post_init(self, context: Any) -> None:
        if self.preferred_start_seconds is not None and self.preferred_end_seconds is not None:
            if self.preferred_end_seconds <= self.preferred_start_seconds:
                raise ValueError("preferred_end_seconds must be greater than preferred_start_seconds")


class PersistedNarrativeBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    tipo: str = Field(min_length=1, max_length=100)
    duracao_segundos: int = Field(gt=0, le=7200)
    conteudo: str = Field(min_length=1, max_length=100_000)
    dicas_visual: str | None = None
    dicas_audio: str | None = None
    visual_queries: list[PersistedVisualQuery] = Field(
        default_factory=list, max_length=5
    )
    purpose: str | None = None
    beats: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    planned_beats: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    claims: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    audio_intent: dict[str, Any] | None = None

    @field_validator("tipo", "conteudo")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class RoteiroEstrutura(BaseModel):
    """Script structure accepted by current consumers and historical rows."""

    model_config = ConfigDict(extra="allow")

    production_script_schema_version: str | None = None
    titulo: str = Field(min_length=1, max_length=300)
    duracao_total_segundos: int = Field(gt=0, le=172_800)
    blocos: list[PersistedNarrativeBlock] = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    referencias: list[str] | None = None
    justificativa_llm: str | None = None
    prompt_trace: dict[str, Any] | None = None
    media_context: dict[str, Any] | None = None
    duration_contract: dict[str, Any] | None = None
    editorial_quality: dict[str, Any] | None = None
    editorial_review: dict[str, Any] | None = None
    evidence_provenance: dict[str, Any] | None = None
    section_audits: dict[str, Any] | None = None
    global_critic: dict[str, Any] | None = None
    generation_run_id: str | None = None
    audit_status: str | None = None
    source_generation_run_id: str | None = None
    inherited_evidence_provenance: dict[str, Any] | None = None

    @field_validator("titulo")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("titulo must not be blank")
        return value

    @model_validator(mode="after")
    def duration_is_coherent(self) -> RoteiroEstrutura:
        if self.duracao_total_segundos < sum(
            item.duracao_segundos for item in self.blocos
        ):
            raise ValueError(
                "duracao_total_segundos cannot be shorter than the block sum"
            )
        return self


def script_content_identity(structure: RoteiroEstrutura) -> str:
    """Hash only current narration-bearing fields; audit metadata is excluded."""

    payload = {
        "title": structure.titulo,
        "blocks": [
            {
                "type": block.tipo,
                "duration_seconds": block.duracao_segundos,
                "content": block.conteudo,
            }
            for block in structure.blocos
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RoteiroBase(BaseModel):
    ideia_id: UUID
    versao: int = Field(default=1, ge=1)
    estrutura: RoteiroEstrutura
    status: str = Field(default="rascunho", max_length=50)
    author_briefing_snapshot: str | None = None
    author_briefing_identity: str | None = Field(default=None, max_length=96)
    parent_roteiro_id: UUID | None = None
    revision_kind: str = Field(default="llm_generation", max_length=32)
    revision_feedback: str | None = None


class RoteiroCreate(RoteiroBase):
    pass


class ScriptCreateRequest(BaseModel):
    """Public manual-create input; persistence provenance is server-owned."""

    ideia_id: UUID
    estrutura: RoteiroEstrutura


class RoteiroUpdate(BaseModel):
    estrutura: RoteiroEstrutura | None = None
    status: str | None = Field(default=None, max_length=50)


class ScriptBlockEdit(BaseModel):
    tipo: str = Field(min_length=1, max_length=100)
    duracao_segundos: int = Field(gt=0, le=7200)
    conteudo: str = Field(min_length=1, max_length=100_000)
    dicas_visual: str | None = None
    dicas_audio: str | None = None

    @field_validator("tipo", "conteudo")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class ScriptEditRevisionRequest(BaseModel):
    titulo: str = Field(min_length=1, max_length=300)
    blocos: list[ScriptBlockEdit] = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    referencias: list[str] | None = None
    edit_summary: str | None = Field(default=None, max_length=5000)

    @field_validator("titulo")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("titulo must not be blank")
        return value


class ScriptRegenerationRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    feedback: str | None = Field(default=None, max_length=10_000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    model_strategy: Literal["flash_only", "standard", "hybrid", "strong"] = "standard"

    @field_validator("feedback")
    @classmethod
    def normalize_optional_feedback(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RoteiroResponse(RoteiroBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_briefing_changed_since_creation: bool | None = None
    criado_em: datetime
    atualizado_em: datetime
