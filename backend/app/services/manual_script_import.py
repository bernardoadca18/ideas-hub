"""Pure normalization and read-only media validation for manual script imports."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.schemas.pov_script import POVScriptDocument
from app.production_profiles import ProductionProfile
from app.schemas.manual_script_import import (
    ManualImportBlockPreview,
    ManualScriptDocument,
    ManualScriptMediaScope,
)
from app.schemas.roteiro import RoteiroEstrutura
from app.services.duration_contract import (
    DurationCalibration,
    count_words,
    evaluate_duration,
    evaluate_editorial_quality,
    predict_duration_seconds,
)
from app.services.media_indexer_client import (
    MediaIndexerClient,
    MediaIndexerError,
    MediaIndexerUnavailableError,
)


class ManualMediaScopeError(ValueError):
    """The requested project/session scope is not a valid canonical scope."""


class ManualMediaScopeUnavailableError(RuntimeError):
    """The Media Indexer could not validate an explicitly requested scope."""


@dataclass(frozen=True, slots=True)
class NormalizedManualScript:
    structure: RoteiroEstrutura
    normalized_payload_sha256: str
    block_previews: tuple[ManualImportBlockPreview, ...]
    word_count: int


PLAIN_TEXT_MANUAL_DRAFT_VERSION = "plain_text_manual_draft_v1"


def normalized_manual_payload_sha256(document: ManualScriptDocument) -> str:
    """Hash normalized external semantics; filenames and server metadata are excluded."""

    canonical = json.dumps(
        document.model_dump(mode="json", exclude_none=True, by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_manual_script(
    document: ManualScriptDocument,
    *,
    calibration: DurationCalibration,
    profile: ProductionProfile,
    target_duration_seconds: int | None,
    content_locale: Literal["pt-BR", "en-US"] = "pt-BR",
) -> NormalizedManualScript:
    """Convert the external V1 shape into the one canonical script structure."""

    imported_storyboard = None
    original_document = document
    if isinstance(document, POVScriptDocument):
        if profile.capabilities.visual_mode != "storyboard":
            raise ValueError("POV JSON requires a storyboard production profile")
        content_locale = document.content_locale
        imported_storyboard = document.canonical_storyboard()
        document = ManualScriptDocument.model_validate({
            "schema": "neovids_manual_script_v1", "title": document.title,
            "blocks": [{"type": b.key, "text": b.text} for b in document.narration.blocks],
        })
    elif profile.capabilities.visual_mode == "storyboard":
        raise ValueError("storyboard_missing: import a neovids_pov_script_v1 document")
    blocks: list[dict[str, Any]] = []
    block_previews: list[ManualImportBlockPreview] = []
    for index, block in enumerate(document.blocks):
        estimated_seconds = max(
            1, math.ceil(predict_duration_seconds(block.text, calibration))
        )
        duration = block.duration_seconds or estimated_seconds
        source: Literal["provided", "estimated"] = (
            "provided" if block.duration_seconds is not None else "estimated"
        )
        blocks.append(
            {
                "tipo": block.type,
                "duracao_segundos": duration,
                # Narration is deliberately carried byte-for-byte as decoded JSON text.
                "conteudo": block.text,
                "visual_queries": [],
            }
        )
        block_previews.append(
            ManualImportBlockPreview(
                index=index,
                type=block.type,
                word_count=count_words(block.text),
                duration_seconds=duration,
                duration_source=source,
            )
        )

    structure = RoteiroEstrutura.model_validate(
        {
            "content_locale": content_locale,
            "titulo": document.title,
            "duracao_total_segundos": sum(
                int(block["duracao_segundos"]) for block in blocks
            ),
            "blocos": blocks,
            "tags": document.tags,
            "referencias": document.references or None,
        }
    )
    payload = structure.model_dump(mode="json")
    if imported_storyboard is not None:
        payload["imported_storyboard"] = imported_storyboard
        payload["production_script_schema_version"] = "neovids_pov_script_v1"
    payload["duration_contract"] = evaluate_duration(
        structure.blocos,
        target_seconds=target_duration_seconds,
        calibration=calibration,
        profile=profile,
    )
    payload["editorial_quality"] = evaluate_editorial_quality(structure.blocos)
    structure = RoteiroEstrutura.model_validate(payload)
    return NormalizedManualScript(
        structure=structure,
        normalized_payload_sha256=(
            normalized_manual_payload_sha256(original_document)
            if content_locale == "pt-BR"
            else hashlib.sha256(
                ("en-US:" + normalized_manual_payload_sha256(original_document)).encode()
            ).hexdigest()
        ),
        block_previews=tuple(block_previews),
        word_count=sum(item.word_count for item in block_previews),
    )


def normalize_plain_text_manual_draft(
    text: str,
    *,
    title: str,
    calibration: DurationCalibration,
    profile: ProductionProfile,
    target_duration_seconds: int | None,
    content_locale: Literal["pt-BR", "en-US"] = "pt-BR",
) -> NormalizedManualScript:
    """Adapt pasted text deterministically without rewriting or trimming it."""

    document = ManualScriptDocument.model_validate(
        {
            "schema": "neovids_manual_script_v1",
            "title": title,
            "blocks": [{"type": "rascunho_humano", "text": text}],
        }
    )
    normalized = normalize_manual_script(
        document,
        content_locale=content_locale,
        calibration=calibration,
        profile=profile,
        target_duration_seconds=target_duration_seconds,
    )
    payload = normalized.structure.model_dump(mode="json")
    payload["manual_draft"] = {
        "adapter_version": PLAIN_TEXT_MANUAL_DRAFT_VERSION,
        "source": "manual_plain_text",
        "original_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "original_char_count": len(text),
    }
    return NormalizedManualScript(
        structure=RoteiroEstrutura.model_validate(payload),
        normalized_payload_sha256=normalized.normalized_payload_sha256,
        block_previews=normalized.block_previews,
        word_count=normalized.word_count,
    )


async def validate_manual_media_scope(
    media: ManualScriptMediaScope | None,
    *,
    client: MediaIndexerClient,
) -> None:
    """Validate project existence and optional session membership over canonical HTTP."""

    if media is None:
        return
    try:
        project = await client.get_project(media.project_id)
        try:
            returned_project_id = UUID(str(project["id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ManualMediaScopeError(
                "Media Indexer returned an invalid project identity"
            ) from exc
        if returned_project_id != media.project_id:
            raise ManualMediaScopeError(
                "Media Indexer project identity does not match project_id"
            )
        if not media.session_ids:
            return
        sessions = await client.list_sessions(media.project_id)
        known = {session.id for session in sessions}
        missing = [
            session_id for session_id in media.session_ids if session_id not in known
        ]
        if missing:
            raise ManualMediaScopeError(
                "session_ids do not all belong to the selected Media Indexer project: "
                + ", ".join(str(value) for value in missing)
            )
    except ManualMediaScopeError:
        raise
    except MediaIndexerUnavailableError as exc:
        raise ManualMediaScopeUnavailableError(
            "Media Indexer is unavailable; explicit media scope was not imported"
        ) from exc
    except MediaIndexerError as exc:
        raise ManualMediaScopeError(f"Invalid Media Indexer scope: {exc}") from exc
