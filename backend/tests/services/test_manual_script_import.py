from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.production_profiles import get_profile
from app.schemas.manual_script_import import ManualScriptImportRequest
from app.schemas.roteiro import RoteiroEstrutura
from app.services.duration_contract import DurationCalibration
from app.services.manual_script_import import (
    ManualMediaScopeError,
    normalize_manual_script,
    normalized_manual_payload_sha256,
    validate_manual_media_scope,
)
from app.services.roteiros.gerador_roteiro import RoteiroGenerator


def calibration() -> DurationCalibration:
    return DurationCalibration(
        version="test-v1",
        identity="calibration-test",
        words_per_minute=120,
        chars_per_second=12,
        sample_count=10,
        source_window="tests",
        generated_at=None,
        fallback=False,
        language="pt-BR",
        voice_profile="test",
        generation_profile="test",
        production_profile="game_analysis",
    )


def idea() -> SimpleNamespace:
    briefing = "Preserve minha leitura autoral."
    return SimpleNamespace(
        id=uuid4(),
        titulo="GTA IV ainda parece vivo",
        nicho_id=None,
        nicho=SimpleNamespace(nome="Games"),
        origem="notas_gameplay",
        status="aprovada",
        author_briefing=briefing,
        author_briefing_identity="author-briefing-test",
        target_duration_seconds=120,
        duration_mode="explicit_target",
    )


def request(
    *, media: bool = False, explicit_duration: bool = False
) -> ManualScriptImportRequest:
    payload: dict = {
        "ideia_id": str(uuid4()),
        "source_filename": "gta-iv.json",
        "script": {
            "schema": "neovids_manual_script_v1",
            "title": "GTA IV fazia algumas coisas melhor",
            "blocks": [
                {
                    "type": "abertura",
                    "text": "Primeira linha.\n\nSegunda linha preservada exatamente.",
                    **({"duration_seconds": 35} if explicit_duration else {}),
                },
                {
                    "type": "conclusao",
                    "text": "A cidade parece viva porque os sistemas colidem.",
                },
            ],
            "tags": [" GTA IV ", "Rockstar", "GTA IV"],
            "references": [],
        },
    }
    if media:
        payload["script"]["media"] = {
            "project_id": str(uuid4()),
            "session_ids": [str(uuid4())],
        }
    return ManualScriptImportRequest.model_validate(payload)


def record(
    *,
    current_idea: SimpleNamespace,
    structure: RoteiroEstrutura,
    version: int,
    revision_kind: str,
    parent_id=None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        ideia_id=current_idea.id,
        ideia=current_idea,
        versao=version,
        estrutura=structure.model_dump(mode="json"),
        status="rascunho",
        author_briefing_snapshot=current_idea.author_briefing,
        author_briefing_identity=current_idea.author_briefing_identity,
        author_briefing_changed_since_creation=False,
        parent_roteiro_id=parent_id,
        revision_kind=revision_kind,
        revision_feedback=None,
        criado_em=now,
        atualizado_em=now,
    )


def configured_generator(current_idea: SimpleNamespace) -> RoteiroGenerator:
    media_client = AsyncMock()
    generator = RoteiroGenerator(AsyncMock(), media_indexer_client=media_client)
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = current_idea
    generator.roteiro_repo = AsyncMock()
    generator._profile_for_idea = AsyncMock(return_value=get_profile("game_analysis"))
    return generator


def test_missing_durations_use_canonical_calibration_and_total_is_coherent() -> None:
    imported = request()
    normalized = normalize_manual_script(
        imported.script,
        calibration=calibration(),
        profile=get_profile("game_analysis"),
        target_duration_seconds=120,
    )
    assert all(
        item.duration_source == "estimated" for item in normalized.block_previews
    )
    assert normalized.structure.duracao_total_segundos == sum(
        block.duracao_segundos for block in normalized.structure.blocos
    )
    assert (
        normalized.structure.duration_contract["calibration"]["identity"]
        == "calibration-test"
    )
    assert normalized.structure.editorial_quality["version"] == "editorial_validator_v2"


def test_explicit_duration_is_preserved_while_other_blocks_are_estimated() -> None:
    imported = request(explicit_duration=True)
    normalized = normalize_manual_script(
        imported.script,
        calibration=calibration(),
        profile=get_profile("game_analysis"),
        target_duration_seconds=120,
    )
    assert normalized.structure.blocos[0].duracao_segundos == 35
    assert [item.duration_source for item in normalized.block_previews] == [
        "provided",
        "estimated",
    ]


def test_payload_identity_is_filename_independent_and_content_sensitive() -> None:
    first = request()
    renamed = first.model_copy(update={"source_filename": "renamed.json"})
    changed = request()
    changed.script.blocks[0].text = "Outro texto narrativo."
    assert normalized_manual_payload_sha256(
        first.script
    ) == normalized_manual_payload_sha256(renamed.script)
    assert normalized_manual_payload_sha256(
        first.script
    ) != normalized_manual_payload_sha256(changed.script)


@pytest.mark.asyncio
async def test_preview_is_read_only_and_reports_server_owned_diagnostics() -> None:
    current_idea = idea()
    imported = request()
    imported.ideia_id = current_idea.id
    generator = configured_generator(current_idea)
    with patch(
        "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
        AsyncMock(return_value=calibration()),
    ):
        preview = await generator.preview_manual_import(imported)
    assert preview.importable is True
    assert preview.idea.production_profile == "game_analysis"
    assert preview.normalized.block_count == 2
    assert preview.normalized.duration_total_seconds == sum(
        item.duration_seconds for item in preview.normalized.blocks
    )
    assert preview.duration["version"] == "script_duration_contract_v1"
    assert preview.visual["status"] == "pending_enrichment"
    assert preview.production_readiness["expected_status_after_import"] == "not_ready"
    generator.roteiro_repo.lock_revision_stream.assert_not_awaited()
    generator.roteiro_repo.create.assert_not_awaited()
    generator.ideia_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_idea_is_rejected_before_any_persistence() -> None:
    generator = configured_generator(idea())
    generator.ideia_repo.get_by_id.return_value = None
    with pytest.raises(ValueError, match="Ideia não encontrada"):
        await generator.preview_manual_import(request())
    generator.roteiro_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_creates_manual_draft_with_only_true_provenance() -> None:
    current_idea = idea()
    imported = request()
    imported.ideia_id = current_idea.id
    generator = configured_generator(current_idea)
    generator.roteiro_repo.get_manual_import_result.return_value = None

    async def create_manual(idea_id, structure, **kwargs):
        assert idea_id == current_idea.id
        return record(
            current_idea=current_idea,
            structure=structure,
            version=1,
            revision_kind="manual_create",
        )

    generator.create_manual_draft = AsyncMock(side_effect=create_manual)
    with patch(
        "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
        AsyncMock(return_value=calibration()),
    ):
        result = await generator.import_manual_script(imported)
    structure = RoteiroEstrutura.model_validate(result.draft.estrutura)
    assert result.created is True
    assert result.current_revision.revision_kind == "manual_create"
    assert structure.manual_import is not None
    assert structure.manual_import.source_filename == "gta-iv.json"
    assert structure.manual_import.source == "manual_file_import"
    assert structure.prompt_trace is None
    assert structure.generation_run_id is None
    assert structure.evidence_provenance is None
    assert structure.section_audits is None
    assert structure.global_critic is None
    assert structure.blocos[0].conteudo == imported.script.blocks[0].text
    generator.roteiro_repo.lock_revision_stream.assert_awaited_once_with(
        current_idea.id
    )


@pytest.mark.asyncio
async def test_duplicate_import_returns_existing_lineage_without_creating_revision() -> (
    None
):
    current_idea = idea()
    imported = request()
    imported.ideia_id = current_idea.id
    generator = configured_generator(current_idea)
    normalized = normalize_manual_script(
        imported.script,
        calibration=calibration(),
        profile=get_profile("game_analysis"),
        target_duration_seconds=120,
    )
    draft = record(
        current_idea=current_idea,
        structure=normalized.structure,
        version=1,
        revision_kind="manual_create",
    )
    generator.roteiro_repo.get_manual_import_result.return_value = (draft, draft)
    generator.create_manual_draft = AsyncMock()
    with patch(
        "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
        AsyncMock(return_value=calibration()),
    ):
        result = await generator.import_manual_script(imported)
    assert result.created is False
    assert result.duplicate is True
    assert result.draft.id == draft.id
    generator.create_manual_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_media_scope_uses_canonical_binding_as_second_revision() -> None:
    current_idea = idea()
    imported = request(media=True)
    imported.ideia_id = current_idea.id
    assert imported.script.media is not None
    generator = configured_generator(current_idea)
    generator.media_indexer_client.get_project.return_value = {
        "id": str(imported.script.media.project_id)
    }
    generator.media_indexer_client.list_sessions.return_value = [
        SimpleNamespace(
            id=imported.script.media.session_ids[0],
            project_id=imported.script.media.project_id,
            label="Gameplay",
            status="ready",
        )
    ]
    generator.roteiro_repo.get_manual_import_result.return_value = None
    normalized = normalize_manual_script(
        imported.script,
        calibration=calibration(),
        profile=get_profile("game_analysis"),
        target_duration_seconds=120,
    )
    draft = record(
        current_idea=current_idea,
        structure=normalized.structure,
        version=1,
        revision_kind="manual_create",
    )
    bound_structure = RoteiroEstrutura.model_validate(
        {
            **normalized.structure.model_dump(mode="json"),
            "media_context": {
                "media_project_id": str(imported.script.media.project_id),
                "media_session_ids": [
                    str(value) for value in imported.script.media.session_ids
                ],
            },
        }
    )
    bound = record(
        current_idea=current_idea,
        structure=bound_structure,
        version=2,
        revision_kind="media_binding",
        parent_id=draft.id,
    )
    generator.create_manual_draft = AsyncMock(return_value=draft)
    generator.bind_media_context_revision = AsyncMock(return_value=bound)
    with patch(
        "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
        AsyncMock(return_value=calibration()),
    ):
        result = await generator.import_manual_script(imported)
    assert result.draft.revision_kind == "manual_create"
    assert result.current_revision.revision_kind == "media_binding"
    assert result.media_binding_applied is True
    binding = generator.bind_media_context_revision.await_args.args[1]
    assert binding.media_context.media_project_id == imported.script.media.project_id


@pytest.mark.asyncio
async def test_invalid_media_scope_fails_before_lineage_is_created() -> None:
    imported = request(media=True)
    assert imported.script.media is not None
    client = AsyncMock()
    client.get_project.return_value = {"id": str(uuid4())}
    with pytest.raises(ManualMediaScopeError, match="does not match"):
        await validate_manual_media_scope(imported.script.media, client=client)

    current_idea = idea()
    imported.ideia_id = current_idea.id
    generator = configured_generator(current_idea)
    generator.media_indexer_client = client
    generator.create_manual_draft = AsyncMock()
    with (
        patch(
            "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
            AsyncMock(return_value=calibration()),
        ),
        pytest.raises(ManualMediaScopeError),
    ):
        await generator.import_manual_script(imported)
    generator.roteiro_repo.lock_revision_stream.assert_not_awaited()
    generator.create_manual_draft.assert_not_awaited()
