"""
Schemas Pydantic para a entidade Nicho.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NichoBase(BaseModel):
    slug: str = Field(..., max_length=80)
    nome: str = Field(..., max_length=120)
    descricao: str | None = None
    prompt_ideacao: str
    prompt_roteiro: str
    categoria_google_trends: str | None = Field(None, max_length=80)
    ativo: bool = True


class NichoCreate(NichoBase):
    pass


class NichoUpdate(BaseModel):
    slug: str | None = Field(None, max_length=80)
    nome: str | None = Field(None, max_length=120)
    descricao: str | None = None
    prompt_ideacao: str | None = None
    prompt_roteiro: str | None = None
    categoria_google_trends: str | None = Field(None, max_length=80)
    ativo: bool | None = None


class NichoResponse(NichoBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True
