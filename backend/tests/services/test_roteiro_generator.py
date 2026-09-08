from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.roteirista import BlocoNarrativo, RoteiroEstruturado
from app.api.routers.roteiros import regenerar_com_feedback
from app.schemas.analise_jogo import AnaliseJogoRequest
from app.schemas.generation import RevisionGenerationRunCreate
from app.schemas.llm_outputs import LLMOutputError
from app.schemas.roteiro import (
    RoteiroEstrutura,
    ScriptEditRevisionRequest,
    ScriptRegenerationRequest,
    script_content_identity,
)
from app.services.author_briefing import author_briefing_identity
from app.services.duration_contract import DurationCalibration
from app.services.roteiros.gerador_roteiro import (
    RoteiroGenerator,
    ScriptGenerationError,
)


def generated_script() -> RoteiroEstruturado:
    return RoteiroEstruturado(
        titulo="Versão gerada",
        duracao_total_segundos=90,
        blocos=[BlocoNarrativo("desenvolvimento", 90, "Narração válida")],
        tags=["teste"],
        prompt_trace={},
    )


def idea(briefing: str | None = "  Minha opinião\r\nsem reescrita.  "):
    return SimpleNamespace(
        id=uuid4(),
        nicho_id=None,
        titulo="Ideia",
        descricao_breve="Descrição",
        author_briefing=briefing,
        author_briefing_identity=author_briefing_identity(briefing),
        status="aprovada",
        eh_continuacao_de=None,
        numero_parte=None,
    )


@pytest.mark.asyncio
async def test_generation_snapshots_verbatim_briefing_and_identity() -> None:
    generator = RoteiroGenerator(AsyncMock())
    current_idea = idea()
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = current_idea
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_latest_version_number_for_update.return_value = 2

    async def create(payload):
        return SimpleNamespace(
            id=uuid4(),
            ideia_id=current_idea.id,
            versao=payload.versao,
            status=payload.status,
        )

    generator.roteiro_repo.create.side_effect = create
    llm = AsyncMock(return_value=generated_script())
    with patch(
        "app.services.roteiros.gerador_roteiro.roteirista_service.gerar_roteiro", llm
    ):
        result = await generator.generate_from_ideia(current_idea.id)

    llm.assert_awaited_once()
    assert llm.await_args.kwargs["author_briefing"] == current_idea.author_briefing
    persisted = generator.roteiro_repo.create.await_args.args[0]
    assert persisted.author_briefing_snapshot == current_idea.author_briefing
    assert persisted.author_briefing_identity == current_idea.author_briefing_identity
    assert persisted.versao == 3
    assert result["versao"] == 3
    generator.ideia_repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_generation_failure_does_not_persist_fake_script_or_change_status() -> (
    None
):
    generator = RoteiroGenerator(AsyncMock())
    current_idea = idea(None)
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = current_idea
    generator.roteiro_repo = AsyncMock()
    with (
        patch(
            "app.services.roteiros.gerador_roteiro.roteirista_service.gerar_roteiro",
            AsyncMock(side_effect=LLMOutputError("malformed_json", "invalid")),
        ),
        pytest.raises(ScriptGenerationError) as error,
    ):
        await generator.generate_from_ideia(current_idea.id)
    assert error.value.category == "malformed_json"
    generator.roteiro_repo.create.assert_not_awaited()
    generator.ideia_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_create_uses_server_owned_revision_and_briefing_snapshot() -> None:
    generator = RoteiroGenerator(AsyncMock())
    current_idea = idea("Contexto autoral")
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = current_idea
    generator._persist_revision = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    structure = RoteiroEstrutura.model_validate(
        {
            "titulo": "Manual",
            "duracao_total_segundos": 20,
            "blocos": [
                {"tipo": "corpo", "duracao_segundos": 20, "conteudo": "Texto manual"}
            ],
        }
    )

    await generator.create_manual_draft(current_idea.id, structure)

    persisted = generator._persist_revision.await_args.kwargs
    assert persisted["ideia"] is current_idea
    assert persisted["revision_kind"] == "manual_create"
    assert persisted["estrutura"].titulo == structure.titulo
    assert persisted["estrutura"].duration_contract["status"] == "estimate_only"
    assert (
        persisted["estrutura"].editorial_quality["version"] == "editorial_validator_v2"
    )


@pytest.mark.asyncio
async def test_game_analysis_passes_separate_briefing_and_snapshots_it() -> None:
    generator = RoteiroGenerator(AsyncMock())
    briefing = "Eu acho que o combate envelheceu mal."
    created_idea = idea(briefing)
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.create.return_value = created_idea
    generator._persist_revision = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid4(), ideia_id=created_idea.id, versao=1, status="rascunho"
        )
    )
    llm = AsyncMock(return_value=generated_script())
    request = AnaliseJogoRequest(
        titulo_provisorio="Análise",
        anotacoes="Nota factual do gameplay",
        author_briefing=briefing,
    )

    with patch(
        "app.services.roteiros.gerador_roteiro.analise_jogos_service.gerar_roteiro_de_notas",
        llm,
    ):
        await generator.generate_from_notas(request)

    assert llm.await_args.kwargs["author_briefing"] == briefing
    assert generator.ideia_repo.create.await_args.args[0].author_briefing == briefing
    persisted = generator._persist_revision.await_args.kwargs
    assert persisted["ideia"].author_briefing == briefing
    assert persisted["revision_kind"] == "game_analysis_generation"


@pytest.mark.asyncio
async def test_game_analysis_provider_failure_creates_no_partial_idea() -> None:
    generator = RoteiroGenerator(AsyncMock())
    generator.ideia_repo = AsyncMock()
    with (
        patch(
            "app.services.roteiros.gerador_roteiro.analise_jogos_service.gerar_roteiro_de_notas",
            AsyncMock(side_effect=ConnectionError("provider offline")),
        ),
        pytest.raises(ScriptGenerationError) as error,
    ):
        await generator.generate_from_notas(
            AnaliseJogoRequest(
                titulo_provisorio="Análise",
                anotacoes="Notas suficientes para o contrato de análise.",
            )
        )

    assert error.value.category == "provider_failure"
    generator.ideia_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_human_edit_invalidates_visual_spans_when_narration_changes() -> None:
    generator = RoteiroGenerator(AsyncMock())
    query_id = uuid4()
    note_id = uuid4()
    source = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        ideia=idea(),
        estrutura={
            "production_script_schema_version": "2.0",
            "titulo": "Original",
            "duracao_total_segundos": 60,
            "blocos": [
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": 60,
                    "conteudo": "Original",
                    "visual_queries": [
                        {
                            "id": str(query_id),
                            "order": 0,
                            "intent": "evidence",
                            "query": "momento registrado",
                            "importance": "required",
                            "source_note_id": str(note_id),
                        }
                    ],
                }
            ],
            "tags": [],
            "editorial_review": {
                "audit_status": "completed",
                "approval_blocked": False,
            },
            "section_audits": {"section-001": {"revision_required": False}},
            "global_critic": {"summary": "Audit antigo"},
            "evidence_provenance": {"generation_run_id": "parent-run"},
            "generation_run_id": "parent-run",
            "media_context": {
                "media_project_id": str(uuid4()),
                "media_session_ids": [str(uuid4())],
            },
        },
    )
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = source
    generator._persist_revision = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    request = ScriptEditRevisionRequest(
        titulo="Editado",
        blocos=[
            {
                "tipo": "desenvolvimento",
                "duracao_segundos": 75,
                "conteudo": "Texto humano corrigido",
                "dicas_visual": "Dica segura",
            }
        ],
        tags=["editado"],
        edit_summary="Removi repetição.",
    )
    await generator.create_human_edit_revision(source.id, request)
    revision = generator._persist_revision.await_args.kwargs
    assert revision["estrutura"].blocos[0].visual_queries == []
    assert revision["revision_kind"] == "human_edit"
    assert revision["parent_roteiro_id"] == source.id
    edited = revision["estrutura"]
    assert edited.editorial_review["audit_status"] == "human_edit_unvalidated"
    assert edited.editorial_review["approval_blocked"] is True
    assert edited.section_audits is None
    assert edited.global_critic is None
    assert edited.evidence_provenance is None
    assert edited.inherited_evidence_provenance == {"generation_run_id": "parent-run"}
    assert edited.generation_run_id is None
    assert edited.source_generation_run_id == "parent-run"
    assert edited.media_context is not None
    assert (
        str(edited.media_context.media_project_id)
        == source.estrutura["media_context"]["media_project_id"]
    )


@pytest.mark.asyncio
async def test_only_latest_draft_can_be_approved() -> None:
    generator = RoteiroGenerator(AsyncMock())
    stale = SimpleNamespace(id=uuid4(), ideia_id=uuid4(), status="rascunho")
    latest = SimpleNamespace(id=uuid4())
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = stale
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = latest
    with pytest.raises(ValueError, match="versão mais recente"):
        await generator.aprovar_roteiro(stale.id)
    generator.roteiro_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_draft_rejection_cannot_reset_idea_state() -> None:
    generator = RoteiroGenerator(AsyncMock())
    stale = SimpleNamespace(id=uuid4(), ideia_id=uuid4(), status="rascunho")
    generator.roteiro_repo = AsyncMock()
    generator.ideia_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = stale
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = SimpleNamespace(
        id=uuid4()
    )

    with pytest.raises(ValueError, match="versão mais recente"):
        await generator.rejeitar_roteiro(stale.id)

    generator.roteiro_repo.update.assert_not_awaited()
    generator.ideia_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_factual_warnings_do_not_block_manual_approval() -> None:
    """Manual approval is sovereign - review warnings are displayed but don't block."""
    generator = RoteiroGenerator(AsyncMock())
    script_id = uuid4()
    structure = {
        "titulo": "Auditado",
        "duracao_total_segundos": 60,
        "blocos": [{"tipo": "corpo", "duracao_segundos": 60, "conteudo": "Texto"}],
        "editorial_review": {
            "audit_status": "completed",
            "editorial_status": "pass",
            "factuality_status": "blocking",
            "approval_blocked": True,  # Review says blocked, but manual approval overrides
        },
    }
    structure["editorial_review"]["audit_content_identity"] = script_content_identity(
        RoteiroEstrutura.model_validate(structure)
    )
    script = SimpleNamespace(
        id=script_id,
        ideia_id=uuid4(),
        status="rascunho",
        estrutura=structure,
    )
    generator.roteiro_repo = AsyncMock()
    generator.ideia_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = script
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = script
    generator.roteiro_repo.update.return_value = SimpleNamespace(status="aprovado")

    result = await generator.aprovar_roteiro(script_id)

    assert result["status"] == "aprovado"
    generator.roteiro_repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_style_warning_does_not_block_human_approval() -> None:
    generator = RoteiroGenerator(AsyncMock())
    script_id = uuid4()
    structure = {
        "titulo": "Auditado",
        "duracao_total_segundos": 60,
        "blocos": [{"tipo": "corpo", "duracao_segundos": 60, "conteudo": "Texto"}],
        "editorial_review": {
            "audit_status": "completed",
            "editorial_status": "warn",
            "factuality_status": "pass",
            "approval_blocked": False,
        },
    }
    structure["editorial_review"]["audit_content_identity"] = script_content_identity(
        RoteiroEstrutura.model_validate(structure)
    )
    script = SimpleNamespace(
        id=script_id,
        ideia_id=uuid4(),
        status="rascunho",
        estrutura=structure,
    )
    generator.roteiro_repo = AsyncMock()
    generator.ideia_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = script
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = script
    generator.roteiro_repo.update.return_value = SimpleNamespace(status="aprovado")

    result = await generator.aprovar_roteiro(script_id)

    assert result["status"] == "aprovado"
    generator.roteiro_repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_v3_script_without_current_audit_can_be_manually_approved() -> None:
    """Manual approval is sovereign - audit unavailability doesn't block approval."""
    generator = RoteiroGenerator(AsyncMock())
    script = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        status="rascunho",
        revision_kind="staged_generation",
        estrutura={
            "titulo": "Sem audit",
            "duracao_total_segundos": 60,
            "blocos": [{"tipo": "corpo", "duracao_segundos": 60, "conteudo": "Texto"}],
            "duration_contract": {"revision_required": False},
        },
    )
    generator.roteiro_repo = AsyncMock()
    generator.ideia_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = script
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = script
    generator.roteiro_repo.update.return_value = SimpleNamespace(status="aprovado")

    result = await generator.aprovar_roteiro(script.id)

    assert result["status"] == "aprovado"
    generator.roteiro_repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_audit_does_not_block_manual_approval() -> None:
    """Manual approval is sovereign - stale audit doesn't block approval."""
    generator = RoteiroGenerator(AsyncMock())
    script = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        status="rascunho",
        revision_kind="human_edit",
        estrutura={
            "titulo": "Editado",
            "duracao_total_segundos": 60,
            "blocos": [{"tipo": "corpo", "duracao_segundos": 60, "conteudo": "Novo"}],
            "duration_contract": {"revision_required": False},
            "editorial_review": {
                "audit_status": "completed",
                "approval_blocked": False,
                "factuality_status": "pass",
                "audit_content_identity": "identity-from-parent",
            },
        },
    )
    generator.roteiro_repo = AsyncMock()
    generator.ideia_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = script
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = script
    generator.roteiro_repo.update.return_value = SimpleNamespace(status="aprovado")

    result = await generator.aprovar_roteiro(script.id)

    assert result["status"] == "aprovado"
    generator.roteiro_repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_regeneration_compatibility_route_delegates_to_v3_run() -> None:
    db = AsyncMock()
    expected = SimpleNamespace(id=uuid4())
    with (
        patch(
            "app.services.script_generation_jobs.ScriptGenerationJobService.enqueue_revision",
            AsyncMock(return_value=expected),
        ) as enqueue,
        patch(
            "app.services.roteiros.gerador_roteiro.roteirista_service.gerar_roteiro",
            AsyncMock(),
        ) as legacy_writer,
    ):
        result = await regenerar_com_feedback(
            uuid4(),
            ScriptRegenerationRequest(
                feedback="Preserve a evidência e encurte o hook."
            ),
            db,
        )

    assert result is expected
    enqueue.assert_awaited_once()
    legacy_writer.assert_not_awaited()


def test_revision_requests_accept_absent_or_blank_human_feedback() -> None:
    durable = RevisionGenerationRunCreate(idempotency_key="diagnostics-only")
    compatibility = ScriptRegenerationRequest(feedback="   ")

    assert durable.feedback is None
    assert compatibility.feedback is None


def test_absent_explicit_duration_remains_estimate_only() -> None:
    current = idea()
    current.target_duration_seconds = None
    assert RoteiroGenerator._target_duration(current) is None


def test_explicit_duration_is_preserved_as_editorial_target() -> None:
    current = idea()
    current.target_duration_seconds = 720
    assert RoteiroGenerator._target_duration(current) == 720


@pytest.mark.asyncio
async def test_duration_policy_is_resolved_from_idea_niche() -> None:
    generator = RoteiroGenerator(AsyncMock())
    current = idea()
    current.nicho_id = uuid4()
    generator.nicho_repo = AsyncMock()
    generator.nicho_repo.get_by_id.return_value = SimpleNamespace(
        perfil_producao="game_analysis"
    )

    profile = await generator._profile_for_idea(current)

    assert profile.id == "game_analysis"


@pytest.mark.asyncio
async def test_duration_revision_loop_is_bounded_and_persists_diagnostics() -> None:
    generator = RoteiroGenerator(AsyncMock())
    current = idea()
    current.target_duration_seconds = 720
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = current
    generator._persist_revision = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid4(), ideia_id=current.id, versao=1, status="rascunho"
        )
    )
    llm = AsyncMock(
        side_effect=[generated_script(), generated_script(), generated_script()]
    )
    calibration = DurationCalibration.fallback_for(
        production_profile="faceless_general"
    )

    with (
        patch(
            "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
            AsyncMock(return_value=calibration),
        ),
        patch(
            "app.services.roteiros.gerador_roteiro.roteirista_service.gerar_roteiro",
            llm,
        ),
    ):
        await generator.generate_from_ideia(current.id)

    assert llm.await_count == 3  # initial + configured maximum of two revisions
    persisted = generator._persist_revision.await_args.kwargs["estrutura"]
    assert persisted.duration_contract["revision_required"] is True
    assert persisted.duration_contract["status"] == "far_below_target"
