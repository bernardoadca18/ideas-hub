"""Strict public contract for importing human-authored production scripts."""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.pov_script import POVScriptDocument
from app.schemas.roteiro import RoteiroResponse

MANUAL_SCRIPT_SCHEMA_VERSION: Literal["neovids_manual_script_v1"] = (
    "neovids_manual_script_v1"
)
MAX_MANUAL_SCRIPT_BYTES = 1_000_000


class ManualScriptBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=100_000)
    duration_seconds: int | None = Field(default=None, gt=0, le=7200, strict=True)

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("block type must not be blank")
        return normalized

    @field_validator("text")
    @classmethod
    def validate_narration(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("block text must not be blank")
        return value


class ManualScriptMediaScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    session_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("session_ids")
    @classmethod
    def unique_sessions(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("session_ids must be unique")
        return value


class ManualScriptDocument(BaseModel):
    """Human-facing input. Host-owned production fields are intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["neovids_manual_script_v1"] = Field(alias="schema")
    title: str = Field(min_length=1, max_length=300)
    blocks: list[ManualScriptBlock] = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    references: list[str] = Field(default_factory=list, max_length=50)
    media: ManualScriptMediaScope | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return cls._normalize_string_list(values, maximum_length=100)

    @field_validator("references")
    @classmethod
    def normalize_references(cls, values: list[str]) -> list[str]:
        return cls._normalize_string_list(values, maximum_length=2_000)

    @staticmethod
    def _normalize_string_list(values: list[str], *, maximum_length: int) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()
            if not item:
                raise ValueError("list items must not be blank")
            if len(item) > maximum_length:
                raise ValueError("list item is too long")
            if item not in seen:
                normalized.append(item)
                seen.add(item)
        return normalized

    @model_validator(mode="after")
    def bounded_payload(self) -> ManualScriptDocument:
        canonical = json.dumps(
            self.model_dump(mode="json", exclude_none=True, by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(canonical.encode("utf-8")) > MAX_MANUAL_SCRIPT_BYTES:
            raise ValueError(
                f"manual script exceeds {MAX_MANUAL_SCRIPT_BYTES} UTF-8 bytes"
            )
        return self


class ManualScriptImportRequest(BaseModel):
    content_locale: Literal["pt-BR", "en-US"] | None = None
    model_config = ConfigDict(extra="forbid")

    ideia_id: UUID
    new_content_niche_id: UUID | None = None
    source_filename: str = Field(min_length=1, max_length=255)
    script: ManualScriptDocument | POVScriptDocument

    @field_validator("source_filename")
    @classmethod
    def safe_json_filename(cls, value: str) -> str:
        normalized = value.strip()
        if (
            not normalized.lower().endswith(".json")
            or "/" in normalized
            or "\\" in normalized
            or "\x00" in normalized
            or normalized in {".", ".."}
        ):
            raise ValueError("source_filename must be a local .json basename")
        return normalized


class ManualImportBlockPreview(BaseModel):
    index: int
    type: str
    word_count: int
    duration_seconds: int
    duration_source: Literal["provided", "estimated"]


class ManualImportIdeaPreview(BaseModel):
    id: UUID
    title: str
    niche: str | None = None
    production_profile: str
    target_duration_seconds: int | None = None
    duration_mode: str


class ManualImportNormalizedPreview(BaseModel):
    pacing: dict[str, Any] | None = None
    title: str
    block_count: int
    scene_count: int = 0
    content_locale: str = "pt-BR"
    word_count: int
    duration_total_seconds: int
    normalized_payload_sha256: str
    blocks: list[ManualImportBlockPreview]


class ManualImportMediaPreview(BaseModel):
    provided: bool
    project_id: UUID | None = None
    session_ids: list[UUID] = Field(default_factory=list)
    scope: Literal["not_provided", "whole_project", "selected_sessions"]


class ManualScriptImportPreviewResponse(BaseModel):
    importable: bool
    schema_version: Literal["neovids_manual_script_v1", "neovids_pov_script_v1"]
    idea: ManualImportIdeaPreview
    normalized: ManualImportNormalizedPreview
    duration: dict[str, Any]
    media_scope: ManualImportMediaPreview
    visual: dict[str, Any]
    production_readiness: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ManualScriptImportResponse(BaseModel):
    created: bool
    duplicate: bool
    normalized_payload_sha256: str
    draft: RoteiroResponse
    current_revision: RoteiroResponse
    media_binding_applied: bool
