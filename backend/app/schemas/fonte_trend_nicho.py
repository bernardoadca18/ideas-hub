"""
Schemas Pydantic para a entidade FonteTrendNicho.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FonteTrendNichoBase(BaseModel):
    nicho_id: UUID
    tipo: str = Field(..., max_length=50)
    identificador: str = Field(..., max_length=200)
    ativo: bool = True


class FonteTrendNichoCreate(FonteTrendNichoBase):
    pass


class FonteTrendNichoUpdate(BaseModel):
    tipo: str | None = Field(None, max_length=50)
    identificador: str | None = Field(None, max_length=200)
    ativo: bool | None = None


class FonteTrendNichoResponse(FonteTrendNichoBase):
    id: UUID
    criado_em: datetime

    class Config:
        from_attributes = True
