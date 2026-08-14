"""
Model SQLAlchemy para a tabela nichos.
"""
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.fonte_trend_nicho import FonteTrendNicho
    from app.models.trend_coletada import TrendColetada
    from app.models.ideia import Ideia


class Nicho(Base, TimestampMixin):
    __tablename__ = "nichos"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_ideacao: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_roteiro: Mapped[str] = mapped_column(Text, nullable=False)
    categoria_google_trends: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relacionamentos
    fontes_trend: Mapped[list["FonteTrendNicho"]] = relationship(
        "FonteTrendNicho",
        back_populates="nicho",
        cascade="all, delete-orphan"
    )
    trends_coletadas: Mapped[list["TrendColetada"]] = relationship(
        "TrendColetada",
        back_populates="nicho",
        cascade="all, delete-orphan"
    )
    ideias: Mapped[list["Ideia"]] = relationship(
        "Ideia",
        back_populates="nicho"
    )
