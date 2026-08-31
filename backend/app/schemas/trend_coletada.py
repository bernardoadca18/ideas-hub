"""
Schemas Pydantic para a entidade TrendColetada.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TrendColetadaBase(BaseModel):
    nicho_id: UUID
    fonte_trend_nicho_id: UUID | None = None
    termo_bruto: str = Field(..., max_length=300)
    fonte: str = Field(..., max_length=50)
    status: str = Field(default="pendente", max_length=50)
    payload_raw: dict = Field(default_factory=dict)


class TrendColetadaCreate(TrendColetadaBase):
    pass


class TrendColetadaUpdate(BaseModel):
    termo_bruto: str | None = Field(None, max_length=300)
    fonte: str | None = Field(None, max_length=50)
    status: str | None = Field(None, max_length=50)
    payload_raw: dict | None = None


class TrendColetadaResponse(TrendColetadaBase):
    id: UUID
    coletado_em: datetime

    class Config:
        from_attributes = True
