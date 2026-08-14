"""
Schemas Pydantic para a entidade Roteiro.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RoteiroBase(BaseModel):
    ideia_id: UUID
    versao: int = Field(default=1)
    estrutura: dict
    status: str = Field(default="rascunho", max_length=50)


class RoteiroCreate(RoteiroBase):
    pass


class RoteiroUpdate(BaseModel):
    versao: int | None = None
    estrutura: dict | None = None
    status: str | None = Field(None, max_length=50)


class RoteiroResponse(RoteiroBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True
