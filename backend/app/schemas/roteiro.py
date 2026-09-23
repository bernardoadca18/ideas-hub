"""Validated persistence and revision contracts for production scripts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PersistedVisualQuery(BaseModel):
    """Backward-compatible persisted VisualQuery, including trusted provenance."""

    model_config = ConfigDict(extra="allow")

    id: UUID | None = None
    order: int = Field(default=0, ge=0)
    intent: str = Field(default="illustration", min_length=1)
    query: str = ""
    narration_excerpt: str | None = None
    importance: str = "preferred"
    source_note_id: UUID | None = None
    preferred_session_id: UUID | None = None
    preferred_start_seconds: float | None = Field(default=None, ge=0)
    preferred_end_seconds: float | None = Field(default=None, ge=0)
    desired_duration_seconds: float | None = Field(default=None, gt=0)
    notes: str | None = None
    visual_beat_id: UUID | None = None
    coverage_start_char: int | None = Field(default=None, ge=0)
    coverage_end_char: int | None = Field(default=None, ge=0)
    coverage_policy_version: str | None = None

    def model_post_init(self, context: Any) -> None:
        if (
            self.preferred_start_seconds is not None
            and self.preferred_end_seconds is not None
            and self.preferred_end_seconds <= self.preferred_start_seconds
        ):
            raise ValueError(
                "preferred_end_seconds must be greater than preferred_start_seconds"
            )
        if (
            self.coverage_start_char is not None or self.coverage_end_char is not None
        ) and (
            self.coverage_start_char is None
            or self.coverage_end_char is None
            or self.coverage_end_char <= self.coverage_start_char
        ):
            raise ValueError(
                "coverage_end_char must be greater than coverage_start_char"
            )


class PersistedNarrativeBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    tipo: str = Field(min_length=1, max_length=100)
    duracao_segundos: int = Field(gt=0, le=7200)
    conteudo: str = Field(min_length=1, max_length=100_000)
    dicas_visual: str | None = None
    dicas_audio: str | None = None
    visual_queries: list[PersistedVisualQuery] = Field(
        default_factory=list, max_length=256
    )
    purpose: str | None = None
    beats: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    planned_beats: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    claims: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    audio_intent: dict[str, Any] | None = None
    display_title: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("tipo", "conteudo")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @field_validator("display_title")
    @classmethod
    def non_blank_display_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("display_title must not be blank")
        return normalized


class StaticImageScope(BaseModel):
    """Explicit opt-in and compact provenance allow-list for source images."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    asset_classes: list[str] = Field(default_factory=list, max_length=16)
    collections: list[str] = Field(default_factory=list, max_length=16)
    source_owners: list[str] = Field(default_factory=list, max_length=16)
    source_classes: list[str] = Field(default_factory=list, max_length=16)

    @field_validator(
        "asset_classes", "collections", "source_owners", "source_classes", mode="before"
    )
    @classmethod
    def normalize_optional_filters(cls, value: Any) -> Any:
        return [] if value is None else value

    @field_validator("asset_classes", "collections", "source_owners", "source_classes")
    @classmethod
    def validate_filters(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 200 for item in normalized):
            raise ValueError("static image filters must contain non-blank values up to 200 chars")
        if len(set(normalized)) != len(normalized):
            raise ValueError("static image filters must be unique")
        return normalized


class ScriptMediaContext(BaseModel):
    """Canonical Media Indexer search scope persisted inside script JSONB."""

    model_config = ConfigDict(extra="allow")

    media_project_id: UUID
    media_session_ids: list[UUID] = Field(default_factory=list)
    static_images: StaticImageScope | None = None

    @field_validator("media_session_ids", mode="before")
    @classmethod
    def normalize_optional_session_ids(cls, value: Any) -> Any:
        return [] if value is None else value

    @field_validator("media_session_ids")
    @classmethod
    def unique_session_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("media_session_ids must be unique")
        return value


class ManualImportProvenance(BaseModel):
    """Server-owned provenance for a validated manual file import."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["neovids_manual_script_v1"]
    source_filename: str = Field(min_length=1, max_length=255)
    normalized_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: Literal["manual_file_import"] = "manual_file_import"


class ManualDraftProvenance(BaseModel):
    """Server-owned provenance for a human draft pasted in Ideas Hub."""

    model_config = ConfigDict(extra="forbid")

    adapter_version: Literal["plain_text_manual_draft_v1"]
    source: Literal["manual_plain_text"] = "manual_plain_text"
    original_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_char_count: int = Field(ge=1, le=100_000)


class RoteiroEstrutura(BaseModel):
    """Script structure accepted by current consumers and historical rows."""

    model_config = ConfigDict(extra="allow")

    content_locale: Literal["pt-BR", "en-US"] = "pt-BR"
    production_script_schema_version: str | None = None
    titulo: str = Field(min_length=1, max_length=300)
    duracao_total_segundos: int = Field(gt=0, le=172_800)
    blocos: list[PersistedNarrativeBlock] = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    referencias: list[str] | None = None
    justificativa_llm: str | None = None
    prompt_trace: dict[str, Any] | None = None
    media_context: ScriptMediaContext | None = None
    duration_contract: dict[str, Any] | None = None
    editorial_quality: dict[str, Any] | None = None
    editorial_review: dict[str, Any] | None = None
    evidence_provenance: dict[str, Any] | None = None
    section_audits: dict[str, Any] | None = None
    global_critic: dict[str, Any] | None = None
    generation_run_id: str | None = None
    audit_status: str | None = None
    source_generation_run_id: str | None = None
    inherited_evidence_provenance: dict[str, Any] | None = None
    visual_readiness: dict[str, Any] | None = None
    manual_import: ManualImportProvenance | None = None
    manual_draft: ManualDraftProvenance | None = None

    @field_validator("titulo")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("titulo must not be blank")
        return value

    @model_validator(mode="after")
    def duration_is_coherent(self) -> RoteiroEstrutura:
        if self.duracao_total_segundos < sum(
            item.duracao_segundos for item in self.blocos
        ):
            raise ValueError(
                "duracao_total_segundos cannot be shorter than the block sum"
            )
        return self


def script_content_identity(structure: RoteiroEstrutura) -> str:
    """Hash only current narration-bearing fields; audit metadata is excluded."""

    payload = {
        "title": structure.titulo,
        "blocks": [
            {
                "type": block.tipo,
                "duration_seconds": block.duracao_segundos,
                "content": block.conteudo,
            }
            for block in structure.blocos
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RoteiroBase(BaseModel):
    ideia_id: UUID
    versao: int = Field(default=1, ge=1)
    estrutura: RoteiroEstrutura
    status: str = Field(default="rascunho", max_length=50)
    author_briefing_snapshot: str | None = None
    author_briefing_identity: str | None = Field(default=None, max_length=96)
    parent_roteiro_id: UUID | None = None
    revision_kind: str = Field(default="llm_generation", max_length=32)
    revision_feedback: str | None = None


class RoteiroCreate(RoteiroBase):
    pass


class ScriptCreateRequest(BaseModel):
    """Public manual-create input; persistence provenance is server-owned."""

    ideia_id: UUID
    estrutura: RoteiroEstrutura


class MediaBindingRequest(BaseModel):
    media_context: ScriptMediaContext


class VisualQueryRepairItem(BaseModel):
    visual_query_id: UUID
    query: str = Field(min_length=1, max_length=2000)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized


class VisualQueryRepairRequest(BaseModel):
    repairs: list[VisualQueryRepairItem] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def unique_query_ids(self) -> VisualQueryRepairRequest:
        ids = [item.visual_query_id for item in self.repairs]
        if len(set(ids)) != len(ids):
            raise ValueError("visual_query_id values must be unique")
        return self


class RoteiroUpdate(BaseModel):
    estrutura: RoteiroEstrutura | None = None
    status: str | None = Field(default=None, max_length=50)


class ScriptBlockEdit(BaseModel):
    tipo: str = Field(min_length=1, max_length=100)
    duracao_segundos: int = Field(gt=0, le=7200)
    conteudo: str = Field(min_length=1, max_length=100_000)
    dicas_visual: str | None = None
    dicas_audio: str | None = None

    @field_validator("tipo", "conteudo")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class ScriptEditRevisionRequest(BaseModel):
    titulo: str = Field(min_length=1, max_length=300)
    blocos: list[ScriptBlockEdit] = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    referencias: list[str] | None = None
    edit_summary: str | None = Field(default=None, max_length=5000)

    @field_validator("titulo")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("titulo must not be blank")
        return value


class ScriptRegenerationRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    feedback: str | None = Field(default=None, max_length=10_000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    model_strategy: Literal["flash_only", "standard", "hybrid", "strong"] = "standard"

    @field_validator("feedback")
    @classmethod
    def normalize_optional_feedback(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RoteiroResponse(RoteiroBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_briefing_changed_since_creation: bool | None = None
    criado_em: datetime
    atualizado_em: datetime


class VisualReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready", "not_required"]
    required: bool = True
    mode: Literal["none", "semantic_match", "background_fill", "storyboard"] = "semantic_match"
    policy_version: str | None = None
    policy_identity: str | None = None
    speakable_content_identity: str | None = None
    block_count: int = Field(default=0, ge=0)
    visual_beat_count: int = Field(default=0, ge=0)
    textual_coverage_ratio: float = Field(default=0, ge=0, le=1)
    missing_ranges: list[dict[str, int]] = Field(default_factory=list)
    overlap_ranges: list[dict[str, int]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class ProductionCapabilitiesResponse(BaseModel):
    delivery_mode: Literal["rendered_video", "manual_edit_package"]
    visual_mode: Literal["none", "semantic_match", "background_fill", "storyboard"]
    requires_media_scope: bool
    caption_policy: Literal["burned_in", "none"]
    render_profile: str | None = None
    version: str = Field(min_length=1)


class ProductionReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    profile: str
    capabilities: ProductionCapabilitiesResponse
    editorial_status: str
    visual: VisualReadinessResponse
    media_scope: dict[str, Any]
    issues: list[dict[str, Any]] = Field(default_factory=list)
