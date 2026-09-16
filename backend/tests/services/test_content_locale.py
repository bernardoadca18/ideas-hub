from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.production_profiles import get_profile
from app.prompts.editorial_v3 import (
    _SPOKEN_PT_BR_POLICY,
    compose_editorial_v3_prompt,
    spoken_language_policy,
)
from app.schemas.ideia import IdeiaCreate, IdeiaUpdate
from app.schemas.roteiro import RoteiroEstrutura
from app.services.script_generation_jobs import ScriptGenerationJobService
from tests.services.test_manual_script_import import (
    calibration,
    configured_generator,
    idea,
    request,
)


def test_idea_locale_and_editorial_policy():
    assert IdeiaCreate(origem="manual", titulo="Title").content_locale == "pt-BR"
    assert (
        IdeiaCreate(
            origem="manual", titulo="Title", content_locale="en-US"
        ).content_locale
        == "en-US"
    )
    assert IdeiaUpdate(status="aprovada").model_dump(exclude_unset=True) == {
        "status": "aprovada"
    }
    with pytest.raises(ValidationError):
        IdeiaCreate(origem="manual", titulo="Title", content_locale="en-GB")
    assert spoken_language_policy("pt-BR") == _SPOKEN_PT_BR_POLICY
    kwargs = dict(
        phase="writing",
        profile=get_profile("faceless_general"),
        task_prompt="Write content",
    )
    assert compose_editorial_v3_prompt(**kwargs) == compose_editorial_v3_prompt(
        **kwargs, content_locale="pt-BR"
    )
    prompt = compose_editorial_v3_prompt(**kwargs, content_locale="en-US")
    assert "natural American English" in prompt.system
    assert "VisualQueries" in prompt.system
    assert _SPOKEN_PT_BR_POLICY not in prompt.system


@pytest.mark.asyncio
async def test_manual_locale_inherits_overrides_and_child_freezes():
    current = idea()
    current.content_locale = "en-US"
    generator = configured_generator(current)
    generator.roteiro_repo.get_latest_version_number_for_update.return_value = 0
    structure = RoteiroEstrutura(
        titulo="Title",
        duracao_total_segundos=30,
        blocos=[
            {
                "tipo": "intro",
                "duracao_segundos": 30,
                "conteudo": "The city feels alive.",
            }
        ],
    )
    assert structure.content_locale == "pt-BR"  # historical fallback
    await generator.create_manual_draft(
        current.id, structure, calibration=calibration()
    )
    saved = generator.roteiro_repo.create.await_args.args[0].estrutura
    assert saved.content_locale == "en-US"
    await generator.create_manual_draft(
        current.id,
        structure.model_copy(update={"content_locale": "pt-BR"}),
        calibration=calibration(),
    )
    assert (
        generator.roteiro_repo.create.await_args.args[0].estrutura.content_locale
        == "pt-BR"
    )
    parent = SimpleNamespace(estrutura=saved.model_dump(mode="json"))
    generator.roteiro_repo.get_by_id.return_value = parent
    current.content_locale = "pt-BR"
    await generator._persist_revision(
        ideia=current,
        estrutura=structure,
        revision_kind="human_edit",
        parent_roteiro_id=uuid4(),
    )
    assert (
        generator.roteiro_repo.create.await_args.args[0].estrutura.content_locale
        == "en-US"
    )
    imported = request()
    imported.ideia_id = current.id
    with patch(
        "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
        AsyncMock(return_value=calibration()),
    ):
        _, _, _, pt = await generator._normalize_manual_import(imported)
        imported.content_locale = "en-US"
        _, _, _, en = await generator._normalize_manual_import(imported)
    assert pt.structure.content_locale == "pt-BR"
    assert en.structure.content_locale == "en-US"
    assert en.normalized_payload_sha256 != pt.normalized_payload_sha256


@pytest.mark.asyncio
async def test_generation_freezes_idea_or_parent_locale():
    current = idea()
    current.content_locale = "en-US"
    current.perfil_producao = "faceless_general"
    current.descricao_breve = "A city simulation"
    session = AsyncMock()
    session.add = MagicMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    service = ScriptGenerationJobService(session, gateway=AsyncMock())
    with (
        patch(
            "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
            AsyncMock(return_value=current),
        ),
        patch(
            "app.services.script_generation_jobs.duration_calibration_client.get",
            AsyncMock(return_value=calibration()),
        ),
        patch(
            "app.services.script_generation_jobs.RoteiroRepository.get_by_id",
            AsyncMock(
                return_value=SimpleNamespace(estrutura={"content_locale": "en-US"})
            ),
        ),
    ):
        run = await service.enqueue(current.id, idempotency_key="locale-test")
        assert run.plan["content_locale"] == "en-US"
        current.content_locale = "pt-BR"
        assert run.plan["content_locale"] == "en-US"
        revision = await service.enqueue(
            current.id,
            idempotency_key="locale-revision",
            generation_intent="revision",
            parent_roteiro_id=uuid4(),
        )
        assert revision.plan["content_locale"] == "en-US"


@pytest.mark.asyncio
async def test_english_planning_requests_and_preserves_english_title(monkeypatch):
    import json
    from tests.services.test_script_generation_jobs import (
        _planning_fixture,
        _result,
        _global_json,
        _batch_json,
    )

    service, _, run, _ = _planning_fixture(monkeypatch)
    run.plan["content_locale"] = "en-US"
    metadata = json.loads(_global_json())
    metadata["titulo"] = "Why This City Feels Alive"
    service._complete = AsyncMock(
        side_effect=[
            _result(json.dumps(metadata), max_tokens=2500),
            _result(
                _batch_json(["section-001", "section-002", "section-003"]),
                max_tokens=4000,
            ),
        ]
    )
    await service._plan(run)
    assert run.plan["content_locale"] == "en-US"
    assert run.plan["planning_state"]["global_output"]["titulo"] == metadata["titulo"]
    for call in service._complete.await_args_list:
        assert "natural American English" in call.kwargs["system_prompt"]
    assert "titulo" in service._complete.await_args_list[0].kwargs["schema"]["required"]
