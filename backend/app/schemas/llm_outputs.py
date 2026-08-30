"""Strict contracts for JSON emitted by Ideas Hub LLM workflows."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


class LLMOutputError(RuntimeError):
    """An upstream model response could not satisfy the requested contract."""

    def __init__(self, category: str, public_message: str):
        super().__init__(public_message)
        self.category = category
        self.public_message = public_message


def extract_json_object(raw: str) -> dict[str, Any]:
    """Decode one model response without accepting non-object JSON."""

    text = raw.strip()
    if not text:
        raise LLMOutputError("empty_output", "O provedor retornou uma resposta vazia.")
    if text.startswith("```json"):
        text = text.removeprefix("```json").split("```", 1)[0]
    elif text.startswith("```"):
        text = text.removeprefix("```").split("```", 1)[0]
    try:
        decoded = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise LLMOutputError("malformed_json", "O provedor retornou JSON inválido.") from exc
    if not isinstance(decoded, dict):
        raise LLMOutputError("contract_validation", "A resposta do provedor não é um objeto JSON.")
    return decoded


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class IdeaRefinementOutput(StrictModel):
    titulo: str = Field(min_length=1, max_length=300)
    descricao_breve: str = Field(max_length=500)
    justificativa: str = Field(max_length=2000)

    @field_validator("titulo")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("titulo must not be blank")
        return value


class RawIdeaOutput(StrictModel):
    titulo: str = Field(min_length=1, max_length=300)
    descricao: str | None = Field(default=None, max_length=500)

    @field_validator("titulo")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("titulo must not be blank")
        return value


class VisualQueryIntent(str, Enum):
    illustration = "illustration"
    evidence = "evidence"
    transition = "transition"
    atmosphere = "atmosphere"
    comparison = "comparison"


class VisualQueryImportance(str, Enum):
    required = "required"
    preferred = "preferred"
    optional = "optional"


class LLMVisualQuery(StrictModel):
    intent: VisualQueryIntent
    query: str = Field(min_length=1, max_length=1000)
    narration_excerpt: str | None = Field(default=None, max_length=1000)
    importance: VisualQueryImportance
    source_note_id: UUID | None = None
    desired_duration_seconds: float | None = Field(default=None, gt=0, le=3600)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class EvidenceTier(str, Enum):
    official_confirmed = "official_confirmed"
    official_observation = "official_observation"
    reliable_secondary = "reliable_secondary"
    leak_authenticated = "leak_authenticated"
    inference = "inference"
    speculation = "speculation"
    unverified = "unverified"
    gameplay_note = "gameplay_note"
    author_opinion = "author_opinion"


class LLMEditorialBeat(StrictModel):
    purpose: str = Field(min_length=1, max_length=1000)
    key_point: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    retention_role: str | None = Field(default=None, max_length=500)


class LLMClaim(StrictModel):
    summary: str = Field(min_length=1, max_length=2000)
    evidence_tier: EvidenceTier
    source_identity: str | None = Field(default=None, max_length=1000)
    confidence: float = Field(ge=0, le=1)


class LLMAudioIntent(StrictModel):
    music_enabled: bool = False
    moods: list[str] = Field(default_factory=list, max_length=8)
    energy: float | None = Field(default=None, ge=0, le=1)
    styles: list[str] = Field(default_factory=list, max_length=8)
    vocals: bool = False
    transition: str | None = Field(default=None, max_length=500)
    sfx_intent: list[str] = Field(default_factory=list, max_length=8)


class LLMNarrativeBlock(StrictModel):
    tipo: str = Field(min_length=1, max_length=100)
    duracao_segundos: int = Field(gt=0, le=7200)
    conteudo: str = Field(min_length=1, max_length=100_000)
    dicas_visual: str | None = Field(default=None, max_length=10_000)
    dicas_audio: str | None = Field(default=None, max_length=10_000)
    visual_queries: list[LLMVisualQuery] = Field(default_factory=list, max_length=5)
    purpose: str | None = Field(default=None, max_length=2000)
    beats: list[LLMEditorialBeat] = Field(default_factory=list, max_length=20)
    claims: list[LLMClaim] = Field(default_factory=list, max_length=50)
    audio_intent: LLMAudioIntent | None = None

    @field_validator("tipo", "conteudo")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class ScriptLLMOutput(StrictModel):
    titulo: str = Field(min_length=1, max_length=300)
    duracao_total_segundos: int = Field(gt=0, le=172_800)
    blocos: list[LLMNarrativeBlock] = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    referencias: list[str] | None = Field(default=None, max_length=100)
    justificativa: str | None = Field(default=None, max_length=10_000)

    @field_validator("titulo")
    @classmethod
    def non_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("titulo must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 200 for item in value):
            raise ValueError("tags must be non-blank and at most 200 characters")
        return value

    @model_validator(mode="after")
    def duration_is_coherent(self) -> ScriptLLMOutput:
        block_duration = sum(item.duracao_segundos for item in self.blocos)
        if self.duracao_total_segundos < block_duration:
            raise ValueError("duracao_total_segundos cannot be shorter than the block sum")
        return self


def validate_model_output(model: type[StrictModel], raw: str) -> StrictModel:
    try:
        return model.model_validate(extract_json_object(raw))
    except LLMOutputError:
        raise
    except ValidationError as exc:
        raise LLMOutputError(
            "contract_validation",
            "A resposta do provedor não atende ao contrato estrutural solicitado.",
        ) from exc
