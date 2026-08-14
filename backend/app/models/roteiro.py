"""
Model SQLAlchemy para a tabela roteiros.
"""
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import SmallInteger, ForeignKey, UniqueConstraint, String, func, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.models.base import Base, TimestampMixin

# Enum nativo do PostgreSQL
StatusRoteiro = Enum("rascunho", "aprovado", "rejeitado", name="status_roteiro", create_type=False)

if TYPE_CHECKING:
    from app.models.ideia import Ideia


class Roteiro(Base, TimestampMixin):
    __tablename__ = "roteiros"
    __table_args__ = (
        UniqueConstraint("ideia_id", "versao", name="uq_roteiro_versao"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    ideia_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ideias.id", ondelete="CASCADE"),
        nullable=False
    )
    versao: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    estrutura: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(StatusRoteiro, nullable=False, default="rascunho")

    # Relacionamentos
    ideia: Mapped["Ideia"] = relationship("Ideia", back_populates="roteiros")
