"""
Schemas Pydantic para a entidade Ideia.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IdeiaBase(BaseModel):
    nicho_id: UUID | None = None
    origem: str = Field(..., max_length=50)
    titulo: str = Field(..., max_length=300)
    descricao_breve: str | None = None
    author_briefing: str | None = None
    target_duration_seconds: int | None = Field(default=None, ge=60, le=28_800)
    status: str = Field(default="rascunho", max_length=50)
    eh_continuacao_de: UUID | None = None
    numero_parte: int | None = Field(default=None, gt=1)
    fonte_trend_id: UUID | None = None
    justificativa_llm: str | None = None


class IdeiaCreate(IdeiaBase):
    pass


class IdeiaUpdate(BaseModel):
    nicho_id: UUID | None = None
    origem: str | None = Field(default=None, max_length=50)
    titulo: str | None = Field(default=None, max_length=300)
    descricao_breve: str | None = None
    author_briefing: str | None = None
    target_duration_seconds: int | None = Field(default=None, ge=60, le=28_800)
    status: str | None = Field(default=None, max_length=50)
    eh_continuacao_de: UUID | None = None
    numero_parte: int | None = Field(default=None, gt=1)
    fonte_trend_id: UUID | None = None
    justificativa_llm: str | None = None


class IdeiaResponse(IdeiaBase):
    id: UUID
    author_briefing_identity: str
    perfil_producao: str | None = None
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True
