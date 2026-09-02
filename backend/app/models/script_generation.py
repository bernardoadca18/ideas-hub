"""Durable, resumable editorial generation runs and bounded section outputs."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.ideia import Ideia
    from app.models.roteiro import Roteiro


class ScriptGenerationRun(Base, TimestampMixin):
    __tablename__ = "script_generation_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    ideia_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ideias.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    roteiro_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roteiros.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_roteiro_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roteiros.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    generation_intent: Mapped[str] = mapped_column(
        String(32), nullable=False, default="initial", server_default="initial"
    )
    revision_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", index=True
    )
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="planning")
    generation_strategy: Mapped[str] = mapped_column(String(48), nullable=False)
    strategy_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    production_profile: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_target_source: Mapped[str] = mapped_column(String(32), nullable=False)
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_dossier: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    continuity_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    model_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    call_usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    total_sections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_sections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    ideia: Mapped[Ideia] = relationship()
    roteiro: Mapped[Roteiro | None] = relationship(foreign_keys=[roteiro_id])
    parent_roteiro: Mapped[Roteiro | None] = relationship(
        foreign_keys=[parent_roteiro_id]
    )
    sections: Mapped[list[ScriptGenerationSection]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ScriptGenerationSection.section_order",
    )


class ScriptGenerationSection(Base, TimestampMixin):
    __tablename__ = "script_generation_sections"
    __table_args__ = (
        UniqueConstraint("run_id", "section_key", name="uq_generation_run_section"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("script_generation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    section_order: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    section_plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    local_validation: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    prompt_provenance: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    output_identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_state: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="clean"
    )

    run: Mapped[ScriptGenerationRun] = relationship(back_populates="sections")
