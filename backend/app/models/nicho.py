"""
Model SQLAlchemy para a tabela nichos.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.production_profiles import DEFAULT_PROFILE_ID

if TYPE_CHECKING:
    from app.models.fonte_trend_nicho import FonteTrendNicho
    from app.models.ideia import Ideia
    from app.models.trend_coletada import TrendColetada


class Nicho(Base, TimestampMixin):
    __tablename__ = "nichos"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_ideacao: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_roteiro: Mapped[str] = mapped_column(Text, nullable=False)
    categoria_google_trends: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Referencia o id de um ProductionProfile registrado em app.production_profiles.
    # Guardado como string livre (não FK/enum de banco) para permitir adicionar novos
    # perfis via código sem migration. Validado a nível de aplicação (schema Pydantic).
    perfil_producao: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DEFAULT_PROFILE_ID,
        server_default=DEFAULT_PROFILE_ID,
    )

    # Relacionamentos
    fontes_trend: Mapped[list["FonteTrendNicho"]] = relationship(
        "FonteTrendNicho", back_populates="nicho", cascade="all, delete-orphan"
    )
    trends_coletadas: Mapped[list["TrendColetada"]] = relationship(
        "TrendColetada", back_populates="nicho", cascade="all, delete-orphan"
    )
    ideias: Mapped[list["Ideia"]] = relationship("Ideia", back_populates="nicho")
