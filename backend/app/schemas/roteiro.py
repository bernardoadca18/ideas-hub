"""Validated persistence and revision contracts for production scripts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
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


class PersistedNarrativeBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    tipo: str = Field(min_length=1, max_length=100)
    duracao_segundos: int = Field(gt=0, le=7200)
    conteudo: str = Field(min_length=1, max_length=100_000)
    dicas_visual: str | None = None
    dicas_audio: str | None = None
    visual_queries: list[PersistedVisualQuery] = Field(default_factory=list, max_length=5)

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

    @field_validator("titulo")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("titulo must not be blank")
        return value

    @model_validator(mode="after")
    def duration_is_coherent(self) -> RoteiroEstrutura:
        if self.duracao_total_segundos < sum(item.duracao_segundos for item in self.blocos):
            raise ValueError("duracao_total_segundos cannot be shorter than the block sum")
        return self


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
    feedback: str = Field(min_length=1, max_length=10_000)

    @field_validator("feedback")
    @classmethod
    def non_blank_feedback(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("feedback must not be blank")
        return value


class RoteiroResponse(RoteiroBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_briefing_changed_since_creation: bool | None = None
    criado_em: datetime
    atualizado_em: datetime
