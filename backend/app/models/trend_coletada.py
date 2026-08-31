"""
Model SQLAlchemy para a tabela trends_coletadas.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Enums nativos do PostgreSQL
FonteTrend = Enum(
    "google_trends",
    "reddit_publico",
    "youtube",
    "rss",
    name="fonte_trend",
    create_type=False,
)
StatusTrend = Enum(
    "pendente", "aprovada", "rejeitada", name="status_trend", create_type=False
)

if TYPE_CHECKING:
    from app.models.fonte_trend_nicho import FonteTrendNicho
    from app.models.ideia import Ideia
    from app.models.nicho import Nicho


class TrendColetada(Base):
    __tablename__ = "trends_coletadas"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    nicho_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("nichos.id", ondelete="CASCADE"),
        nullable=False,
    )
    fonte_trend_nicho_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("fontes_trend_nicho.id", ondelete="SET NULL"),
        nullable=True,
    )
    termo_bruto: Mapped[str] = mapped_column(String(300), nullable=False)
    fonte: Mapped[str] = mapped_column(FonteTrend, nullable=False)
    status: Mapped[str] = mapped_column(StatusTrend, nullable=False, default="pendente")
    payload_raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relacionamentos
    nicho: Mapped["Nicho"] = relationship("Nicho", back_populates="trends_coletadas")
    fonte_trend_nicho: Mapped["FonteTrendNicho | None"] = relationship(
        "FonteTrendNicho", back_populates="trends_coletadas"
    )
    ideias: Mapped[list["Ideia"]] = relationship("Ideia", back_populates="fonte_trend")
