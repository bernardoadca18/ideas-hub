"""
Model SQLAlchemy para a tabela ideias.
"""
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import String, Text, SmallInteger, ForeignKey, CheckConstraint, func, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from pgvector.sqlalchemy import Vector

from app.models.base import Base, TimestampMixin

# Enums nativos do PostgreSQL
OrigemIdeia = Enum("manual", "trend", "llm", name="origem_ideia", create_type=False)
StatusIdeia = Enum("rascunho", "aprovada", "rejeitada", "em_roteiro", "roteirizada", "produzida", name="status_ideia", create_type=False)

if TYPE_CHECKING:
    from app.models.nicho import Nicho
    from app.models.trend_coletada import TrendColetada
    from app.models.roteiro import Roteiro


class Ideia(Base, TimestampMixin):
    __tablename__ = "ideias"
    __table_args__ = (
        CheckConstraint(
            "numero_parte IS NULL OR numero_parte > 1",
            name="chk_numero_parte"
        ),
        CheckConstraint(
            "(eh_continuacao_de IS NULL AND numero_parte IS NULL) OR "
            "(eh_continuacao_de IS NOT NULL AND numero_parte IS NOT NULL)",
            name="chk_continuacao"
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    nicho_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("nichos.id", ondelete="SET NULL"),
        nullable=True
    )
    origem: Mapped[str] = mapped_column(OrigemIdeia, nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    descricao_breve: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(StatusIdeia, nullable=False, default="rascunho")
    eh_continuacao_de: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ideias.id", ondelete="SET NULL"),
        nullable=True
    )
    numero_parte: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    fonte_trend_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trends_coletadas.id", ondelete="SET NULL"),
        nullable=True
    )
    justificativa_llm: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relacionamentos
    nicho: Mapped["Nicho | None"] = relationship("Nicho", back_populates="ideias")
    fonte_trend: Mapped["TrendColetada | None"] = relationship("TrendColetada", back_populates="ideias")
    ideia_continuacao: Mapped["Ideia | None"] = relationship(
        "Ideia",
        remote_side=[id],
        foreign_keys=[eh_continuacao_de]
    )
    roteiros: Mapped[list["Roteiro"]] = relationship(
        "Roteiro",
        back_populates="ideia",
        cascade="all, delete-orphan"
    )
