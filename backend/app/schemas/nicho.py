"""
Schemas Pydantic para a entidade Nicho.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.production_profiles import DEFAULT_PROFILE_ID, is_valid_profile_id


class NichoBase(BaseModel):
    slug: str = Field(..., max_length=80)
    nome: str = Field(..., max_length=120)
    descricao: str | None = None
    prompt_ideacao: str
    prompt_roteiro: str
    categoria_google_trends: str | None = Field(None, max_length=80)
    ativo: bool = True
    perfil_producao: str = Field(default=DEFAULT_PROFILE_ID, max_length=50)

    @field_validator("perfil_producao")
    @classmethod
    def valida_perfil_producao(cls, v: str) -> str:
        if not is_valid_profile_id(v):
            raise ValueError(
                f"perfil_producao '{v}' desconhecido. Veja app.production_profiles.list_profiles()."
            )
        return v


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
    perfil_producao: str | None = Field(None, max_length=50)

    @field_validator("perfil_producao")
    @classmethod
    def valida_perfil_producao(cls, v: str | None) -> str | None:
        if v is not None and not is_valid_profile_id(v):
            raise ValueError(
                f"perfil_producao '{v}' desconhecido. Veja app.production_profiles.list_profiles()."
            )
        return v


class NichoResponse(NichoBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True
