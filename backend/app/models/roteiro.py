"""
Model SQLAlchemy para a tabela roteiros.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Enum nativo do PostgreSQL
StatusRoteiro = Enum(
    "rascunho", "aprovado", "rejeitado", name="status_roteiro", create_type=False
)

if TYPE_CHECKING:
    from app.models.ideia import Ideia


class Roteiro(Base, TimestampMixin):
    __tablename__ = "roteiros"
    __table_args__ = (UniqueConstraint("ideia_id", "versao", name="uq_roteiro_versao"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    ideia_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ideias.id", ondelete="CASCADE"),
        nullable=False,
    )
    versao: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    estrutura: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        StatusRoteiro, nullable=False, default="rascunho"
    )
    author_briefing_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_briefing_identity: Mapped[str | None] = mapped_column(
        String(96), nullable=True
    )
    parent_roteiro_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roteiros.id", ondelete="SET NULL"),
        nullable=True,
    )
    revision_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="llm_generation", server_default="legacy"
    )
    revision_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relacionamentos
    ideia: Mapped["Ideia"] = relationship("Ideia", back_populates="roteiros")
    parent_roteiro: Mapped["Roteiro | None"] = relationship(
        "Roteiro", remote_side=[id], foreign_keys=[parent_roteiro_id]
    )

    @property
    def author_briefing_changed_since_creation(self) -> bool | None:
        if self.author_briefing_identity is None:
            return None
        return self.author_briefing_identity != self.ideia.author_briefing_identity
