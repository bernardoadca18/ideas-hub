from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents.roteirista import BlocoNarrativo, RoteiroEstruturado
from app.schemas.analise_jogo import AnaliseJogoRequest
from app.schemas.llm_outputs import LLMOutputError
from app.schemas.roteiro import RoteiroEstrutura, ScriptEditRevisionRequest
from app.services.author_briefing import author_briefing_identity
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
            id=uuid4(), ideia_id=current_idea.id, versao=payload.versao, status=payload.status
        )

    generator.roteiro_repo.create.side_effect = create
    llm = AsyncMock(return_value=generated_script())
    with patch("app.services.roteiros.gerador_roteiro.roteirista_service.gerar_roteiro", llm):
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
async def test_generation_failure_does_not_persist_fake_script_or_change_status() -> None:
    generator = RoteiroGenerator(AsyncMock())
    current_idea = idea(None)
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = current_idea
    generator.roteiro_repo = AsyncMock()
    with patch(
        "app.services.roteiros.gerador_roteiro.roteirista_service.gerar_roteiro",
        AsyncMock(side_effect=LLMOutputError("malformed_json", "invalid")),
    ), pytest.raises(ScriptGenerationError) as error:
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
    assert persisted == {
        "ideia": current_idea,
        "estrutura": structure,
        "revision_kind": "manual_create",
    }


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
    with patch(
        "app.services.roteiros.gerador_roteiro.analise_jogos_service.gerar_roteiro_de_notas",
        AsyncMock(side_effect=ConnectionError("provider offline")),
    ), pytest.raises(ScriptGenerationError) as error:
        await generator.generate_from_notas(
            AnaliseJogoRequest(
                titulo_provisorio="Análise",
                anotacoes="Notas suficientes para o contrato de análise.",
            )
        )

    assert error.value.category == "provider_failure"
    generator.ideia_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_human_edit_creates_revision_and_preserves_visual_provenance() -> None:
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
            "blocos": [{
                "tipo": "desenvolvimento",
                "duracao_segundos": 60,
                "conteudo": "Original",
                "visual_queries": [{
                    "id": str(query_id),
                    "order": 0,
                    "intent": "evidence",
                    "query": "momento registrado",
                    "importance": "required",
                    "source_note_id": str(note_id),
                }],
            }],
            "tags": [],
        },
    )
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = source
    generator._persist_revision = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    request = ScriptEditRevisionRequest(
        titulo="Editado",
        blocos=[{
            "tipo": "desenvolvimento",
            "duracao_segundos": 75,
            "conteudo": "Texto humano corrigido",
            "dicas_visual": "Dica segura",
        }],
        tags=["editado"],
        edit_summary="Removi repetição.",
    )
    await generator.create_human_edit_revision(source.id, request)
    revision = generator._persist_revision.await_args.kwargs
    persisted_query = revision["estrutura"].blocos[0].visual_queries[0]
    assert persisted_query.id == query_id
    assert persisted_query.source_note_id == note_id
    assert revision["revision_kind"] == "human_edit"
    assert revision["parent_roteiro_id"] == source.id


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
    generator.roteiro_repo.get_latest_version_by_ideia.return_value = SimpleNamespace(id=uuid4())

    with pytest.raises(ValueError, match="versão mais recente"):
        await generator.rejeitar_roteiro(stale.id)

    generator.roteiro_repo.update.assert_not_awaited()
    generator.ideia_repo.update.assert_not_awaited()
