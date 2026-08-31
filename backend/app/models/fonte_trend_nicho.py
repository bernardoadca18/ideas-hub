"""
Model SQLAlchemy para a tabela fontes_trend_nicho.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Enum nativo do PostgreSQL
TipoFonteNicho = Enum(
    "reddit_publico",
    "rss",
    "youtube_categoria",
    name="tipo_fonte_nicho",
    create_type=False,
)

if TYPE_CHECKING:
    from app.models.nicho import Nicho
    from app.models.trend_coletada import TrendColetada


class FonteTrendNicho(Base):
    __tablename__ = "fontes_trend_nicho"
    __table_args__ = (
        UniqueConstraint("nicho_id", "tipo", "identificador", name="uq_fonte_nicho"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    nicho_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("nichos.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(TipoFonteNicho, nullable=False)
    identificador: Mapped[str] = mapped_column(String(200), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relacionamentos
    nicho: Mapped["Nicho"] = relationship("Nicho", back_populates="fontes_trend")
    trends_coletadas: Mapped[list["TrendColetada"]] = relationship(
        "TrendColetada", back_populates="fonte_trend_nicho"
    )
