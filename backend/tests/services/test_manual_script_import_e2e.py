"""Acceptance path: manual JSON converges on the normal production-script contract."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.production_profiles import get_profile
from app.schemas.manual_script_import import ManualScriptImportRequest
from app.schemas.roteiro import RoteiroEstrutura
from app.services.duration_contract import DurationCalibration
from app.services.production_readiness import evaluate_production_readiness
from app.services.roteiros.gerador_roteiro import RoteiroGenerator
from app.services.visual_requirements import speakable_content_identity


@pytest.mark.asyncio
async def test_manual_import_can_reach_the_orchestrator_snapshot_contract() -> None:
    project_id = uuid4()
    session_id = uuid4()
    imported = ManualScriptImportRequest.model_validate(
        {
            "ideia_id": str(uuid4()),
            "source_filename": "gta-iv.json",
            "script": {
                "schema": "neovids_manual_script_v1",
                "title": "GTA IV ainda parece vivo",
                "blocks": [
                    {
                        "type": "abertura",
                        "text": "Existe uma coisa estranha quando você volta para GTA IV.",
                        "duration_seconds": 25,
                    },
                    {
                        "type": "conclusao",
                        "text": "A colisão entre os sistemas transforma a cidade em história.",
                        "duration_seconds": 25,
                    },
                ],
                "media": {
                    "project_id": str(project_id),
                    "session_ids": [str(session_id)],
                },
            },
        }
    )
    calibration = DurationCalibration.fallback_for(production_profile="game_analysis")
    profile = get_profile("game_analysis")
    current_idea = SimpleNamespace(
        id=imported.ideia_id,
        titulo="GTA IV",
        descricao_breve="Análise sistêmica",
        author_briefing="Preservar a narração do operador.",
        nicho_id=None,
        origem="notas_gameplay",
        status="aprovada",
        author_briefing_identity="author-briefing-test",
        target_duration_seconds=None,
        duration_mode="content_driven",
    )
    generator = RoteiroGenerator(AsyncMock(), media_indexer_client=AsyncMock())
    revisions: list[SimpleNamespace] = []

    generator.roteiro_repo = AsyncMock()
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = current_idea
    generator._profile_for_idea = AsyncMock(return_value=profile)
    generator.media_indexer_client.get_project.return_value = {"id": str(project_id)}
    generator.media_indexer_client.list_sessions.return_value = [
        SimpleNamespace(id=session_id)
    ]
    generator.roteiro_repo.get_manual_import_result.return_value = None

    async def create_revision(data):
        now = datetime.now(UTC)
        structure = RoteiroEstrutura.model_validate(data.estrutura)
        created = SimpleNamespace(
            id=uuid4(),
            ideia_id=data.ideia_id,
            ideia=current_idea,
            versao=data.versao,
            estrutura=structure.model_dump(mode="json"),
            status=data.status,
            author_briefing_snapshot=data.author_briefing_snapshot,
            author_briefing_identity=data.author_briefing_identity,
            author_briefing_changed_since_creation=False,
            parent_roteiro_id=data.parent_roteiro_id,
            revision_kind=data.revision_kind,
            revision_feedback=data.revision_feedback,
            criado_em=now,
            atualizado_em=now,
        )
        revisions.append(created)
        return created

    async def get_by_id(roteiro_id):
        return next((item for item in revisions if item.id == roteiro_id), None)

    async def update(roteiro_id, data):
        current = await get_by_id(roteiro_id)
        assert current is not None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(current, field, value)
        return current

    generator.roteiro_repo.create.side_effect = create_revision
    generator.roteiro_repo.get_by_id.side_effect = get_by_id
    generator.roteiro_repo.get_latest_version_number_for_update.side_effect = (
        lambda _idea_id: len(revisions)
    )
    generator.roteiro_repo.get_latest_version_by_ideia.side_effect = lambda _idea_id: (
        revisions[-1] if revisions else None
    )
    generator.roteiro_repo.update.side_effect = update

    with patch(
        "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
        AsyncMock(return_value=calibration),
    ):
        preview = await generator.preview_manual_import(imported)
        assert preview.importable is True
        assert revisions == []
        imported_result = await generator.import_manual_script(imported)

    assert imported_result.draft.revision_kind == "manual_create"
    assert imported_result.current_revision.revision_kind == "media_binding"
    assert imported_result.media_binding_applied is True
    assert len(revisions) == 2
    bound_structure = RoteiroEstrutura.model_validate(
        imported_result.current_revision.estrutura
    )
    exact_narration = [block.text for block in imported.script.blocks]
    assert [block.conteudo for block in bound_structure.blocos] == exact_narration
    assert bound_structure.manual_import is not None
    assert bound_structure.prompt_trace is None
    assert bound_structure.generation_run_id is None
    assert bound_structure.evidence_provenance is None

    async def deterministic_visual_provider(**kwargs):
        prompt = kwargs["messages"][1]["content"]
        orders = [int(value) for value in re.findall(r'"beat_order":\s*(\d+)', prompt)]
        return MagicMock(
            content=json.dumps(
                {
                    "visual_queries": [
                        {
                            "beat_order": order,
                            "intent": "illustration",
                            "query": f"Gameplay de GTA IV para o trecho {order}",
                            "importance": "preferred",
                            "source_note_id": None,
                            "notes": None,
                        }
                        for order in orders
                    ]
                }
            )
        )

    before_identity = speakable_content_identity(bound_structure.blocos)
    with patch(
        "app.services.llm_gateway.llm_gateway.complete",
        deterministic_visual_provider,
    ):
        enriched_revision = await generator.create_visual_enrichment_revision(
            imported_result.current_revision.id
        )
    enriched = RoteiroEstrutura.model_validate(enriched_revision.estrutura)
    assert enriched_revision.revision_kind == "visual_enrichment"
    assert enriched_revision.parent_roteiro_id == imported_result.current_revision.id
    assert speakable_content_identity(enriched.blocos) == before_identity
    assert [block.conteudo for block in enriched.blocos] == exact_narration
    assert enriched.manual_import is not None
    assert enriched.prompt_trace is None
    assert enriched.generation_run_id is None
    assert enriched.evidence_provenance is None

    approval = await generator.aprovar_roteiro(enriched_revision.id)
    assert approval["status"] == "aprovado"

    readiness = evaluate_production_readiness(
        enriched, script_status=approval["status"], profile=profile
    )
    assert readiness["status"] == "ready"

    # Fields validated by the current Orchestrator IdeasHubScript boundary.
    snapshot = enriched.model_dump(mode="json")
    assert snapshot["titulo"]
    assert snapshot["duracao_total_segundos"] > 0
    assert snapshot["duracao_total_segundos"] >= sum(
        block["duracao_segundos"] for block in snapshot["blocos"]
    )
    assert all(
        block["tipo"]
        and block["conteudo"]
        and block["duracao_segundos"] > 0
        and block["visual_queries"]
        for block in snapshot["blocos"]
    )
