from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.production_profiles import get_profile
from app.schemas.llm_outputs import LLMVisualBeatQuery
from app.schemas.roteiro import (
    MediaBindingRequest,
    RoteiroEstrutura,
    ScriptMediaContext,
    StaticImageScope,
    VisualQueryRepairRequest,
    script_content_identity,
)
from app.services.production_readiness import evaluate_production_readiness
from app.services.roteiros.gerador_roteiro import RoteiroGenerator
from app.services.visual_requirements import (
    materialize_written_visual_queries,
    segment_visual_beats,
)

PROJECT_ID = uuid4()
SESSION_ID = uuid4()


def _ready_structure(*, media: bool) -> RoteiroEstrutura:
    content = "GTA IV usa física sistêmica para criar situações emergentes."
    beats = segment_visual_beats(
        section_key="section-001", content=content, duration_seconds=20
    )
    queries = materialize_written_visual_queries(
        generation_run_id=uuid4(),
        section_key="section-001",
        duration_seconds=20,
        content=content,
        generated=[
            LLMVisualBeatQuery(
                beat_order=beat.order,
                intent="evidence",
                query="Gameplay de GTA IV demonstrando física sistêmica",
                importance="required",
            )
            for beat in beats
        ],
        evidence_dossier={},
        beats=beats,
    )
    return RoteiroEstrutura.model_validate(
        {
            "titulo": "Análise de GTA IV",
            "duracao_total_segundos": 20,
            "blocos": [
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": 20,
                    "conteudo": content,
                    "visual_queries": [item.to_dict() for item in queries],
                    "claims": [{"id": "claim-1"}],
                }
            ],
            "tags": ["física"],
            "referencias": ["nota do autor"],
            "editorial_review": {"audit_status": "completed"},
            "evidence_provenance": {"source": "notes"},
            "media_context": (
                {
                    "media_project_id": str(PROJECT_ID),
                    "media_session_ids": [str(SESSION_ID)],
                }
                if media
                else None
            ),
        }
    )


def _source(structure: RoteiroEstrutura):
    idea = SimpleNamespace(
        id=uuid4(),
        nicho_id=None,
        origem="notas_gameplay",
        titulo="GTA IV",
        descricao_breve="Análise de GTA IV",
        author_briefing="Preservar a identidade de GTA IV",
    )
    return SimpleNamespace(
        id=uuid4(),
        ideia_id=idea.id,
        ideia=idea,
        status="aprovado",
        estrutura=structure.model_dump(mode="json"),
    )


@pytest.mark.asyncio
async def test_media_binding_creates_metadata_only_child_revision() -> None:
    before = _ready_structure(media=False)
    source = _source(before)
    generator = RoteiroGenerator(AsyncMock())
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = source
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = source
    generator._persist_revision = AsyncMock(return_value=SimpleNamespace(id=uuid4()))

    await generator.bind_media_context_revision(
        source.id,
        MediaBindingRequest(
            media_context={
                "media_project_id": PROJECT_ID,
                "media_session_ids": [SESSION_ID],
            }
        ),
    )

    persisted = generator._persist_revision.await_args.kwargs
    after = persisted["estrutura"]
    assert persisted["revision_kind"] == "media_binding"
    assert persisted["parent_roteiro_id"] == source.id
    assert script_content_identity(after) == script_content_identity(before)
    assert after.tags == before.tags
    assert after.referencias == before.referencias
    assert after.editorial_review == before.editorial_review
    assert after.evidence_provenance == before.evidence_provenance
    assert after.blocos[0].claims == before.blocos[0].claims
    assert [item.id for item in after.blocos[0].visual_queries] == [
        item.id for item in before.blocos[0].visual_queries
    ]
    assert [item.visual_beat_id for item in after.blocos[0].visual_queries] == [
        item.visual_beat_id for item in before.blocos[0].visual_queries
    ]
    assert after.media_context == ScriptMediaContext(
        media_project_id=PROJECT_ID, media_session_ids=[SESSION_ID]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source_state", ["missing", "stale", "noop"])
async def test_media_binding_rejects_invalid_source_state(source_state: str) -> None:
    structure = _ready_structure(media=source_state == "noop")
    source = _source(structure)
    generator = RoteiroGenerator(AsyncMock())
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = (
        None if source_state == "missing" else source
    )
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = (
        SimpleNamespace(id=uuid4()) if source_state == "stale" else source
    )
    generator._persist_revision = AsyncMock()
    request = MediaBindingRequest(
        media_context={
            "media_project_id": PROJECT_ID,
            "media_session_ids": [SESSION_ID],
        }
    )
    with pytest.raises(ValueError):
        await generator.bind_media_context_revision(source.id, request)
    generator._persist_revision.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {"media_project_id": "invalid", "media_session_ids": [str(SESSION_ID)]},
        {"media_project_id": str(PROJECT_ID), "media_session_ids": ["invalid"]},
        {
            "media_project_id": str(PROJECT_ID),
            "media_session_ids": [str(SESSION_ID), str(SESSION_ID)],
        },
    ],
)
def test_media_context_rejects_invalid_ids_or_duplicate_sessions(
    payload: dict,
) -> None:
    with pytest.raises(ValidationError):
        ScriptMediaContext.model_validate(payload)


@pytest.mark.parametrize("session_ids", [None, []])
def test_empty_session_scope_means_search_the_whole_project(session_ids) -> None:
    context = ScriptMediaContext.model_validate(
        {"media_project_id": str(PROJECT_ID), "media_session_ids": session_ids}
    )
    assert context.media_session_ids == []


def test_legacy_media_context_keeps_static_images_disabled() -> None:
    context = ScriptMediaContext.model_validate(
        {"media_project_id": str(PROJECT_ID), "media_session_ids": []}
    )
    assert context.static_images is None
    assert "static_images" not in context.model_dump(mode="json", exclude_none=True)


def test_static_image_scope_is_explicit_and_serializable() -> None:
    context = ScriptMediaContext.model_validate(
        {
            "media_project_id": str(PROJECT_ID),
            "media_session_ids": [str(SESSION_ID)],
            "static_images": {
                "enabled": True,
                "asset_classes": [" official_screenshot ", "official_artwork"],
                "collections": ["screenshots"],
                "source_owners": ["studio"],
                "source_classes": ["official"],
            },
        }
    )
    assert context.static_images == StaticImageScope(
        enabled=True,
        asset_classes=["official_screenshot", "official_artwork"],
        collections=["screenshots"],
        source_owners=["studio"],
        source_classes=["official"],
    )
    assert context.model_dump(mode="json")["static_images"]["enabled"] is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("asset_classes", ["official", "official"]),
        ("collections", [" "]),
        ("source_owners", ["x" * 201]),
    ],
)
def test_static_image_scope_rejects_duplicate_or_invalid_filters(field, value) -> None:
    with pytest.raises(ValidationError):
        StaticImageScope.model_validate({"enabled": True, field: value})


@pytest.mark.asyncio
async def test_static_image_binding_is_metadata_only() -> None:
    before = _ready_structure(media=True)
    source = _source(before)
    generator = RoteiroGenerator(AsyncMock())
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = source
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = source
    generator._persist_revision = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    query_ids = [item.id for item in before.blocos[0].visual_queries]

    await generator.bind_media_context_revision(
        source.id,
        MediaBindingRequest(
            media_context={
                "media_project_id": PROJECT_ID,
                "media_session_ids": [SESSION_ID],
                "static_images": {
                    "enabled": True,
                    "asset_classes": ["official_screenshot"],
                },
            }
        ),
    )

    after = generator._persist_revision.await_args.kwargs["estrutura"]
    assert script_content_identity(after) == script_content_identity(before)
    assert [item.id for item in after.blocos[0].visual_queries] == query_ids
    assert after.blocos[0].claims == before.blocos[0].claims
    assert after.media_context.static_images.enabled is True


def test_production_readiness_is_profile_aware() -> None:
    profile = get_profile("game_analysis")
    missing = evaluate_production_readiness(
        _ready_structure(media=False), script_status="aprovado", profile=profile
    )
    assert missing["status"] == "not_ready"
    assert missing["media_scope"]["status"] == "missing"
    assert {item["code"] for item in missing["issues"]} == {"media_scope_missing"}

    ready = evaluate_production_readiness(
        _ready_structure(media=True), script_status="aprovado", profile=profile
    )
    assert ready["status"] == "ready"
    assert ready["media_scope"]["status"] == "ready"

    scope_optional = evaluate_production_readiness(
        _ready_structure(media=False),
        script_status="aprovado",
        profile=replace(profile, requires_media_scope=False),
    )
    assert scope_optional["status"] == "ready"
    assert scope_optional["media_scope"]["status"] == "not_required"


def test_draft_with_complete_resources_still_needs_editorial_approval() -> None:
    report = evaluate_production_readiness(
        _ready_structure(media=True),
        script_status="rascunho",
        profile=get_profile("game_analysis"),
    )
    assert report["status"] == "not_ready"
    assert report["issues"] == [{"code": "editorial_approval_missing"}]


@pytest.mark.asyncio
async def test_visual_query_repair_changes_only_selected_query_text() -> None:
    before = _ready_structure(media=True)
    source = _source(before)
    query_id = before.blocos[0].visual_queries[0].id
    assert query_id is not None
    generator = RoteiroGenerator(AsyncMock())
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = source
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = source
    generator._persist_revision = AsyncMock(return_value=SimpleNamespace(id=uuid4()))

    await generator.repair_visual_queries_revision(
        source.id,
        VisualQueryRepairRequest(
            repairs=[
                {
                    "visual_query_id": query_id,
                    "query": "Gameplay de GTA IV com colisões e física sistêmica",
                }
            ]
        ),
    )

    persisted = generator._persist_revision.await_args.kwargs
    after = persisted["estrutura"]
    assert persisted["revision_kind"] == "visual_query_repair"
    assert persisted["parent_roteiro_id"] == source.id
    assert script_content_identity(after) == script_content_identity(before)
    assert after.media_context == before.media_context
    assert after.blocos[0].visual_queries[0].id == query_id
    assert (
        after.blocos[0].visual_queries[0].visual_beat_id
        == before.blocos[0].visual_queries[0].visual_beat_id
    )
    assert (
        after.blocos[0].visual_queries[0].coverage_start_char,
        after.blocos[0].visual_queries[0].coverage_end_char,
    ) == (
        before.blocos[0].visual_queries[0].coverage_start_char,
        before.blocos[0].visual_queries[0].coverage_end_char,
    )
