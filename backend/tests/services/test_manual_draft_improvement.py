from __future__ import annotations

import hashlib
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.production_profiles import get_profile
from app.schemas.roteiro import RoteiroEstrutura
from app.services.duration_contract import DurationCalibration
from app.services.manual_script_import import normalize_plain_text_manual_draft
from app.services.script_generation_jobs import ScriptGenerationJobService


def _calibration() -> DurationCalibration:
    return DurationCalibration.fallback_for(production_profile="faceless_general")


def _idea() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        titulo="GTA VI e a evolução dos NPCs",
        descricao_breve="Análise comparativa.",
        status="aprovada",
        perfil_producao="faceless_general",
        origem="manual",
        nicho_id=None,
        author_briefing="Preserve a leitura autoral.",
        target_duration_seconds=720,
        duration_mode="explicit_target",
    )


def _draft_record(idea: SimpleNamespace, structure: RoteiroEstrutura) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        ideia_id=idea.id,
        ideia=idea,
        versao=1,
        estrutura=structure.model_dump(mode="json"),
        status="rascunho",
        author_briefing_snapshot=idea.author_briefing,
        author_briefing_identity="briefing-id",
        author_briefing_changed_since_creation=False,
        parent_roteiro_id=None,
        revision_kind="manual_create",
        revision_feedback=None,
        criado_em=datetime.now(UTC),
        atualizado_em=datetime.now(UTC),
    )


class _NestedTransaction(AbstractAsyncContextManager[None]):
    def __init__(self) -> None:
        self.error_type: type[BaseException] | None = None

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.error_type = exc_type
        return False


def _query_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def test_plain_text_adapter_preserves_original_whitespace_and_duration_diagnostics() -> None:
    text = "  Minha abertura.\n\nComparação GTA IV / GTA V.\nConclusão com duas linhas.  "

    normalized = normalize_plain_text_manual_draft(
        text,
        title="Título da Idea",
        calibration=_calibration(),
        profile=get_profile("faceless_general"),
        target_duration_seconds=720,
    )

    assert normalized.structure.blocos[0].conteudo == text
    assert normalized.structure.blocos[0].tipo == "rascunho_humano"
    assert normalized.structure.duration_contract is not None
    assert normalized.structure.duration_contract["target_duration_seconds"] == 720
    assert normalized.structure.duration_contract["revision_required"] is True


@pytest.mark.asyncio
async def test_composite_flow_persists_manual_parent_then_enqueues_revision() -> None:
    idea = _idea()
    text = "A tese é esta.\n\nPreserve este exemplo concreto."
    repository = AsyncMock()
    repository.get_by_id = AsyncMock()
    repository.lock_revision_stream = AsyncMock()
    idea_repository = AsyncMock()
    idea_repository.get_by_id.return_value = idea
    nested = _NestedTransaction()
    session = MagicMock()
    session.execute = AsyncMock(return_value=_query_result(None))
    session.begin_nested.return_value = nested
    session.flush = AsyncMock()
    generator = MagicMock()
    generator._profile_for_idea = AsyncMock(
        return_value=get_profile("faceless_general")
    )
    generator._target_duration.return_value = 720

    async def create_manual_draft(idea_id, structure, **kwargs):
        assert idea_id == idea.id
        return _draft_record(idea, structure)

    generator.create_manual_draft = AsyncMock(side_effect=create_manual_draft)
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=idea.id,
        generation_intent="revision",
        parent_roteiro_id=None,
    )
    service = ScriptGenerationJobService(session)
    service.enqueue_revision = AsyncMock(return_value=run)  # type: ignore[method-assign]

    with (
        patch(
            "app.services.script_generation_jobs.RoteiroRepository",
            return_value=repository,
        ),
        patch(
            "app.services.script_generation_jobs.IdeiaRepository",
            return_value=idea_repository,
        ),
        patch(
            "app.services.roteiros.gerador_roteiro.RoteiroGenerator",
            return_value=generator,
        ),
        patch(
            "app.services.script_generation_jobs.duration_calibration_client.get",
            AsyncMock(return_value=_calibration()),
        ),
    ):
        result = await service.enqueue_manual_draft_improvement(
            idea.id,
            draft_text=text,
            idempotency_key="manual-draft-submit-001",
            feedback="  Não remova o exemplo.  ",
        )

    persisted = RoteiroEstrutura.model_validate(result["draft"].estrutura)
    assert result["created"] is True
    assert persisted.blocos[0].conteudo == text
    assert persisted.manual_draft is not None
    assert persisted.manual_draft.source == "manual_plain_text"
    assert persisted.manual_draft.original_text_sha256 == hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()
    service.enqueue_revision.assert_awaited_once_with(
        result["draft"].id,
        idempotency_key="manual-draft-submit-001",
        feedback="Não remova o exemplo.",
        model_strategy="standard",
    )
    assert nested.error_type is None


@pytest.mark.asyncio
async def test_same_idempotency_key_returns_original_parent_and_run() -> None:
    idea = _idea()
    text = "Rascunho humano exato."
    normalized = normalize_plain_text_manual_draft(
        text,
        title=idea.titulo,
        calibration=_calibration(),
        profile=get_profile("faceless_general"),
        target_duration_seconds=720,
    )
    payload = normalized.structure.model_dump(mode="json")
    payload["manual_draft"] = {
        "adapter_version": "plain_text_manual_draft_v1",
        "source": "manual_plain_text",
        "original_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "original_char_count": len(text),
    }
    draft = _draft_record(idea, RoteiroEstrutura.model_validate(payload))
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=idea.id,
        generation_intent="revision",
        parent_roteiro_id=draft.id,
        revision_feedback="Preserve a conclusão.",
    )
    repository = AsyncMock()
    repository.lock_revision_stream = AsyncMock()
    repository.get_by_id.return_value = draft
    session = MagicMock()
    session.execute = AsyncMock(return_value=_query_result(run))
    session.begin_nested = MagicMock()
    service = ScriptGenerationJobService(session)

    with patch(
        "app.services.script_generation_jobs.RoteiroRepository",
        return_value=repository,
    ):
        result = await service.enqueue_manual_draft_improvement(
            idea.id,
            draft_text=text,
            idempotency_key="manual-draft-submit-002",
            feedback="Preserve a conclusão.",
        )

    assert result == {
        "created": False,
        "duplicate": True,
        "draft": draft,
        "run": run,
    }
    session.begin_nested.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_failure_rolls_back_composite_savepoint() -> None:
    idea = _idea()
    repository = AsyncMock()
    repository.lock_revision_stream = AsyncMock()
    idea_repository = AsyncMock()
    idea_repository.get_by_id.return_value = idea
    nested = _NestedTransaction()
    session = MagicMock()
    session.execute = AsyncMock(return_value=_query_result(None))
    session.begin_nested.return_value = nested
    generator = MagicMock()
    generator._profile_for_idea = AsyncMock(
        return_value=get_profile("faceless_general")
    )
    generator._target_duration.return_value = 720
    placeholder = normalize_plain_text_manual_draft(
        "Texto",
        title=idea.titulo,
        calibration=_calibration(),
        profile=get_profile("faceless_general"),
        target_duration_seconds=720,
    ).structure
    generator.create_manual_draft = AsyncMock(
        return_value=_draft_record(idea, placeholder)
    )
    service = ScriptGenerationJobService(session)
    service.enqueue_revision = AsyncMock(  # type: ignore[method-assign]
        side_effect=ValueError("idea already has active generation run")
    )

    with (
        patch(
            "app.services.script_generation_jobs.RoteiroRepository",
            return_value=repository,
        ),
        patch(
            "app.services.script_generation_jobs.IdeiaRepository",
            return_value=idea_repository,
        ),
        patch(
            "app.services.roteiros.gerador_roteiro.RoteiroGenerator",
            return_value=generator,
        ),
        patch(
            "app.services.script_generation_jobs.duration_calibration_client.get",
            AsyncMock(return_value=_calibration()),
        ),
        pytest.raises(ValueError, match="active generation run"),
    ):
        await service.enqueue_manual_draft_improvement(
            idea.id,
            draft_text="Texto",
            idempotency_key="manual-draft-submit-003",
        )

    assert nested.error_type is ValueError


@pytest.mark.asyncio
async def test_game_analysis_manual_parent_uses_profile_and_bound_backbone() -> None:
    idea = _idea()
    idea.origem = "notas_gameplay"
    idea.perfil_producao = None
    text = "Vi o evento durante a gameplay.\n\nNão tenho certeza sobre a causa."
    normalized = normalize_plain_text_manual_draft(
        text,
        title=idea.titulo,
        calibration=_calibration(),
        profile=get_profile("game_analysis"),
        target_duration_seconds=720,
    )
    payload = normalized.structure.model_dump(mode="json")
    payload["manual_draft"] = {
        "adapter_version": "plain_text_manual_draft_v1",
        "source": "manual_plain_text",
        "original_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "original_char_count": len(text),
    }
    source = _draft_record(idea, RoteiroEstrutura.model_validate(payload))
    repository = AsyncMock()
    repository.get_by_id.return_value = source
    repository.get_latest_version_by_ideia.return_value = source
    session = AsyncMock()
    run = SimpleNamespace(
        plan={
            "sections": [
                {"key": "section-001"},
                {"key": "section-002"},
            ]
        }
    )
    service = ScriptGenerationJobService(session)
    service.enqueue = AsyncMock(return_value=run)  # type: ignore[method-assign]

    with (
        patch(
            "app.services.script_generation_jobs.RoteiroRepository",
            return_value=repository,
        ),
        patch(
            "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
            AsyncMock(return_value=idea),
        ),
    ):
        result = await service.enqueue_revision(
            source.id,
            idempotency_key="game-analysis-manual-revision",
        )

    assert result is run
    assert service.enqueue.await_args.kwargs["profile_id_override"] == "game_analysis"
    assert service.enqueue.await_args.kwargs["generation_intent"] == "revision"
    assert run.plan["revision_brief"]["parent"]["roteiro_id"] == str(source.id)
    assert "human_backbone" in run.plan["revision_brief"]
    assignments = run.plan["revision_brief"]["human_backbone"]["assignments"]
    assert "".join(item["current_content"] for item in assignments) == text
    session.refresh.assert_awaited_once_with(run)
