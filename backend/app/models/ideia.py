"""
Model SQLAlchemy para a tabela ideias.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Enums nativos do PostgreSQL
OrigemIdeia = Enum(
    "manual", "trend", "llm", "notas_gameplay", name="origem_ideia", create_type=False
)
StatusIdeia = Enum(
    "rascunho",
    "aprovada",
    "rejeitada",
    "em_roteiro",
    "roteirizada",
    "produzida",
    name="status_ideia",
    create_type=False,
)

if TYPE_CHECKING:
    from app.models.nicho import Nicho
    from app.models.roteiro import Roteiro
    from app.models.trend_coletada import TrendColetada


class Ideia(Base, TimestampMixin):
    __tablename__ = "ideias"
    __table_args__ = (
        CheckConstraint(
            "numero_parte IS NULL OR numero_parte > 1", name="chk_numero_parte"
        ),
        CheckConstraint(
            "(eh_continuacao_de IS NULL AND numero_parte IS NULL) OR "
            "(eh_continuacao_de IS NOT NULL AND numero_parte IS NOT NULL)",
            name="chk_continuacao",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    nicho_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("nichos.id", ondelete="SET NULL"),
        nullable=True,
    )
    content_locale: Mapped[str] = mapped_column(
        String(5), nullable=False, default="pt-BR", server_default="pt-BR"
    )
    origem: Mapped[str] = mapped_column(OrigemIdeia, nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    descricao_breve: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_briefing: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_duration_seconds: Mapped[int | None] = mapped_column(nullable=True)
    duration_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_target_source: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    status: Mapped[str] = mapped_column(StatusIdeia, nullable=False, default="rascunho")
    eh_continuacao_de: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ideias.id", ondelete="SET NULL"),
        nullable=True,
    )
    numero_parte: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    fonte_trend_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trends_coletadas.id", ondelete="SET NULL"),
        nullable=True,
    )
    justificativa_llm: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relacionamentos
    nicho: Mapped["Nicho | None"] = relationship("Nicho", back_populates="ideias")
    fonte_trend: Mapped["TrendColetada | None"] = relationship(
        "TrendColetada", back_populates="ideias"
    )
    ideia_continuacao: Mapped["Ideia | None"] = relationship(
        "Ideia", remote_side=[id], foreign_keys=[eh_continuacao_de]
    )
    roteiros: Mapped[list["Roteiro"]] = relationship(
        "Roteiro", back_populates="ideia", cascade="all, delete-orphan"
    )

    @property
    def author_briefing_identity(self) -> str:
        from app.services.author_briefing import author_briefing_identity

        return author_briefing_identity(self.author_briefing)

    @property
    def perfil_producao(self) -> str | None:
        """Read-only profile projection owned by the idea's niche."""

        return self.nicho.perfil_producao if self.nicho is not None else None
