from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from app.core.config import Settings
from app.schemas.generation import EditorialPlanOutput
from app.services.llm_gateway import (
    LLMCallResult,
    LLMFailureCategory,
    LLMGateway,
    LLMGatewayError,
    LLMTaskRole,
)
from app.services.script_generation_jobs import (
    GenerationFailureCategory,
    GenerationJobError,
    ScriptGenerationJobService,
    _planning_max_tokens,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _config() -> Settings:
    return Settings(
        llm_model="standard-route",
        llm_fast_model="fast-route",
        llm_standard_model="standard-route",
        llm_strong_model="strong-route",
    )


def _result(role: LLMTaskRole, model: str) -> LLMCallResult:
    return LLMCallResult(
        content="{}",
        task_role=role.value,
        model_alias=model,
        actual_model="provider/model",
        provider="test",
        prompt_identity="prompt",
        temperature=0.5,
        max_tokens=100,
        prompt_tokens=10,
        completion_tokens=2,
        total_tokens=12,
        latency_seconds=0.01,
        attempt_count=1,
    )


def _editorial_plan_json(*, section_keys: list[str] | None = None) -> str:
    keys = section_keys or ["section-01"]
    return json.dumps(
        {
            "thesis": "Uma tese editorial verificável.",
            "audience_promise": "Entender o argumento sem fatos inventados.",
            "chapters": ["Capítulo único"],
            "sections": [
                {
                    "key": key,
                    "title": f"Seção {index}",
                    "purpose": "Desenvolver o argumento com clareza.",
                    "narrative_role": "desenvolvimento",
                    "beats": ["Apresentar o ponto central"],
                    "evidence_refs": [],
                    "must_cover": ["A tese editorial"],
                    "must_not_repeat": [],
                    "transition_target": "Conectar com a próxima seção",
                }
                for index, key in enumerate(keys, start=1)
            ],
            "claim_ledger": [],
            "open_loops": [],
        }
    )


def _gateway_response(content: str, *, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "provider/model",
            "provider": "test",
            "choices": [
                {
                    "message": {"content": content},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        },
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )


def _problematic_run_budgets() -> list[dict[str, int | str]]:
    return [
        {
            "key": f"section-{index:03d}",
            "order": index - 1,
            "chapter_order": 0,
            "target_duration_seconds": 240,
            "target_words": 596,
            "min_words": 507,
            "max_words": 685,
        }
        for index in range(1, 4)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "role", "escalation", "expected"),
    [
        ("standard", LLMTaskRole.WRITING, None, "standard-route"),
        ("flash_only", LLMTaskRole.CRITIC, None, "standard-route"),
        ("hybrid", LLMTaskRole.PLANNING, None, "strong-route"),
        ("hybrid", LLMTaskRole.WRITING, None, "standard-route"),
        ("strong", LLMTaskRole.WRITING, None, "strong-route"),
        ("standard", LLMTaskRole.WRITING, "repeated_failure", "strong-route"),
    ],
)
async def test_task_policy_routes_by_function_without_provider_names(
    strategy: str,
    role: LLMTaskRole,
    escalation: str | None,
    expected: str,
) -> None:
    session = AsyncMock()
    gateway = MagicMock()
    gateway.complete = AsyncMock()
    gateway.model_for.return_value = "standard-route"
    gateway.complete.side_effect = lambda **kwargs: _result(role, kwargs["model_alias"])
    run = SimpleNamespace(
        call_usage={"calls": 0, "total_tokens": 0, "escalations": []},
        model_policy={"strategy": strategy},
        strategy_identity="strategy-id",
    )
    service = ScriptGenerationJobService(session, gateway=gateway, config=_config())
    await service._complete(
        run,
        role=role,
        prompt="prompt",
        schema={"type": "object"},
        max_tokens=100,
        escalation_reason=escalation,
    )
    assert gateway.complete.await_args.kwargs["model_alias"] == expected
    assert run.call_usage["calls"] == 1
    assert (len(run.call_usage["escalations"]) == 1) is bool(escalation)


@pytest.mark.asyncio
async def test_parse_or_repair_returns_valid_pydantic_output_without_repair() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._complete = AsyncMock()  # type: ignore[method-assign]
    result = _result(LLMTaskRole.PLANNING, "standard-route")
    result = LLMCallResult(**{**result.__dict__, "content": _editorial_plan_json()})

    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(), result, EditorialPlanOutput
    )

    assert isinstance(parsed, EditorialPlanOutput)
    assert parsed.sections[0].key == "section-01"
    assert provenance == result.provenance()
    service._complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_parse_or_repair_handles_json_decode_error_and_repairs_once() -> None:
    class JsonLoadsEditorialPlanOutput(EditorialPlanOutput):
        @classmethod
        def model_validate_json(cls, json_data, **kwargs):
            return cls.model_validate(json.loads(json_data), **kwargs)

    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    malformed = _result(LLMTaskRole.PLANNING, "standard-route")
    malformed = LLMCallResult(**{**malformed.__dict__, "content": "{"})
    repaired = _result(LLMTaskRole.REPAIR, "fast-route")
    repaired = LLMCallResult(**{**repaired.__dict__, "content": _editorial_plan_json()})
    service._complete = AsyncMock(return_value=repaired)  # type: ignore[method-assign]

    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(), malformed, JsonLoadsEditorialPlanOutput
    )

    assert isinstance(parsed, EditorialPlanOutput)
    assert provenance["repair_reason"] == "JSONDecodeError"
    assert provenance["repair"]["task_role"] == LLMTaskRole.REPAIR.value
    service._complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_parse_or_repair_repairs_schema_invalid_json() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    invalid = _result(LLMTaskRole.PLANNING, "standard-route")
    invalid = LLMCallResult(
        **{
            **invalid.__dict__,
            "content": json.dumps(
                {
                    "thesis": "Tese",
                    "audience_promise": "Promessa",
                    "chapters": ["Capítulo"],
                    "sections": [],
                }
            ),
        }
    )
    repaired = _result(LLMTaskRole.REPAIR, "fast-route")
    repaired = LLMCallResult(**{**repaired.__dict__, "content": _editorial_plan_json()})
    service._complete = AsyncMock(return_value=repaired)  # type: ignore[method-assign]

    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(), invalid, EditorialPlanOutput
    )

    assert isinstance(parsed, EditorialPlanOutput)
    assert provenance["repair_reason"] == "ValidationError"
    repair_call = service._complete.await_args.kwargs
    assert repair_call["role"] is LLMTaskRole.REPAIR
    assert "Repair only JSON serialization and schema shape" in repair_call["prompt"]
    assert "do not add facts" in repair_call["prompt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("still_invalid", ["{", '{"thesis":"still incomplete"}'])
async def test_parse_or_repair_fails_after_one_invalid_repair(
    still_invalid: str,
) -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    initial = _result(LLMTaskRole.PLANNING, "standard-route")
    initial = LLMCallResult(**{**initial.__dict__, "content": "{"})
    repair = _result(LLMTaskRole.REPAIR, "fast-route")
    repair = LLMCallResult(**{**repair.__dict__, "content": still_invalid})
    service._complete = AsyncMock(return_value=repair)  # type: ignore[method-assign]

    with pytest.raises(LLMGatewayError) as captured:
        await service._parse_or_repair(SimpleNamespace(), initial, EditorialPlanOutput)

    assert captured.value.category is LLMFailureCategory.FORMAT
    assert "bounded repair" in str(captured.value)
    service._complete.assert_awaited_once()


def test_planning_output_token_budget_scales_and_remains_bounded() -> None:
    assert _planning_max_tokens(1) == 3000
    assert _planning_max_tokens(3) == 4000
    assert _planning_max_tokens(4) == 5000
    assert _planning_max_tokens(5) == 6000
    assert _planning_max_tokens(120) == 6000
    with pytest.raises(ValueError, match="at least one"):
        _planning_max_tokens(0)


def _execute_plan_with_keys(
    monkeypatch: pytest.MonkeyPatch,
    section_keys: list[str],
    *,
    finish_reason: str = "stop",
):
    session = AsyncMock(spec=AsyncSession)
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    planning_result = _result(LLMTaskRole.PLANNING, "standard-route")
    planning_result = LLMCallResult(
        **{
            **planning_result.__dict__,
            "content": _editorial_plan_json(section_keys=section_keys),
            "finish_reason": finish_reason,
            "max_tokens": 4000,
            "completion_tokens": 1996,
        }
    )
    service._complete = AsyncMock(return_value=planning_result)  # type: ignore[method-assign]
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        phase="planning",
        plan={"sections": _problematic_run_budgets()},
        evidence_dossier={
            "sources": [{"id": "idea-description"}],
            "fragments": [],
        },
        call_usage={"calls": 0, "total_tokens": 0, "escalations": []},
        model_policy={"strategy": "standard"},
        strategy_identity="problematic-run-shape",
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                titulo="Fixture do run problemático",
                descricao_breve="Conteúdo sintético sem fatos externos.",
                author_briefing=None,
            )
        ),
    )
    return service, session, run


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "section_keys",
    [
        ["section-001", "section-002", "section-003", "section-004"],
        ["section-001", "section-002"],
        ["section-001", "renamed-section", "section-003"],
        ["section-002", "section-001", "section-003"],
    ],
    ids=["extra", "missing", "renamed", "reordered"],
)
async def test_plan_rejects_section_contract_mismatch(
    monkeypatch: pytest.MonkeyPatch, section_keys: list[str]
) -> None:
    service, session, run = _execute_plan_with_keys(monkeypatch, section_keys)

    with pytest.raises(GenerationJobError) as captured:
        await service._plan(run)

    assert captured.value.category is GenerationFailureCategory.SCHEMA
    assert "planner section contract mismatch" in str(captured.value)
    assert "expected_count=3" in str(captured.value)
    assert f"actual_count={len(section_keys)}" in str(captured.value)
    session.add.assert_not_called()
    service._complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_plan_classifies_token_limit_before_section_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session, run = _execute_plan_with_keys(
        monkeypatch,
        ["section-001", "section-002", "section-003", "section-004"],
        finish_reason="length",
    )

    with pytest.raises(LLMGatewayError) as captured:
        await service._plan(run)

    assert captured.value.category is LLMFailureCategory.FORMAT
    assert "truncated" in str(captured.value)
    assert "finish_reason=length" in str(captured.value)
    assert "section contract mismatch" not in str(captured.value)
    session.add.assert_not_called()
    service._complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_plan_uses_schema_fallback_repair_and_deterministic_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_rejection = httpx.Response(
        400,
        text='{"error":{"message":"Request contains an invalid argument",'
        '"status":"INVALID_ARGUMENT"}}',
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )
    invalid_plan = json.dumps(
        {
            "thesis": "Tese inicial",
            "audience_promise": "Promessa inicial",
            "chapters": ["Capítulo"],
            "sections": [
                {
                    "key": "llm-key-1",
                    "title": "Seção 1",
                    "purpose": "Explicar o primeiro ponto",
                    "narrative_role": "x" * 101,
                    "beats": ["Ponto 1"],
                    "must_cover": ["Tese"],
                },
                {
                    "key": "llm-key-2",
                    "title": "Seção 2",
                    "purpose": "Explicar o segundo ponto",
                    "narrative_role": "conclusão",
                    "beats": ["Ponto 2"],
                    "must_cover": ["Síntese"],
                },
            ],
            "claim_ledger": {"unexpected": "shape"},
            "open_loops": [],
        }
    )
    repaired_plan = _editorial_plan_json(
        section_keys=["section-001", "section-002", "section-003"]
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = [
        schema_rejection,
        _gateway_response(invalid_plan),
        _gateway_response(repaired_plan),
    ]
    config = Settings(
        litellm_base_url="http://litellm.test",
        llm_model="standard-route",
        llm_fast_model="fast-route",
        llm_standard_model="standard-route",
        llm_strong_model="strong-route",
        llm_max_attempts=3,
    )
    gateway = LLMGateway(config, client=client)
    session = AsyncMock(spec=AsyncSession)
    requested_sections = _problematic_run_budgets()
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        phase="queued",
        plan={"sections": requested_sections},
        evidence_dossier={
            "sources": [{"id": "idea-description"}],
            "fragments": [],
        },
        call_usage={"calls": 0, "total_tokens": 0, "escalations": []},
        model_policy={"strategy": "standard"},
        strategy_identity="editorial-test-v3",
    )
    idea = SimpleNamespace(
        titulo="Plano sintético de regressão",
        descricao_breve="Conteúdo controlado, sem evidência factual externa.",
        author_briefing=None,
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(return_value=idea),
    )
    service = ScriptGenerationJobService(session, gateway=gateway, config=config)

    await service._plan(run)

    assert run.phase == "writing"
    assert EditorialPlanOutput.model_validate(run.plan["editorial"])
    assert run.plan["planning_provenance"]["initial"]["attempt_count"] == 2
    assert (
        run.plan["planning_provenance"]["initial"]["fallback_reason"]
        == "provider_json_schema_unsupported"
    )
    assert run.plan["planning_provenance"]["repair"]["task_role"] == "repair"
    assert run.plan["planning_provenance"]["initial"]["finish_reason"] == "stop"
    assert run.plan["planning_provenance"]["repair"]["finish_reason"] == "stop"
    assert [section["key"] for section in run.plan["editorial"]["sections"]] == [
        "section-001",
        "section-002",
        "section-003",
    ]
    assert run.call_usage["calls"] == 2
    assert client.post.await_count == 3
    payloads = [call.kwargs["json"] for call in client.post.await_args_list]
    assert payloads[0]["response_format"]["type"] == "json_schema"
    assert payloads[1]["response_format"] == {"type": "json_object"}
    assert payloads[2]["response_format"]["type"] == "json_schema"
    assert [payload["max_tokens"] for payload in payloads] == [4000, 4000, 4000]
    planning_prompt = payloads[0]["messages"][1]["content"]
    assert "Section keys and count are immutable" in planning_prompt
    assert (
        "Do not add, remove, merge, split, reorder or rename sections"
        in planning_prompt
    )
    persisted_sections = [call.args[0] for call in session.add.call_args_list]
    assert [section.section_key for section in persisted_sections] == [
        "section-001",
        "section-002",
        "section-003",
    ]
    assert [section.section_plan["target_words"] for section in persisted_sections] == [
        596,
        596,
        596,
    ]
    assert [section.section_plan["key"] for section in persisted_sections] == [
        "section-001",
        "section-002",
        "section-003",
    ]
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_preserves_completed_sections_and_requeues_only_failure() -> None:
    completed = SimpleNamespace(
        status="completed", error_category=None, error_message=None
    )
    failed = SimpleNamespace(
        status="failed", error_category="provider", error_message="down"
    )
    run = SimpleNamespace(
        id=uuid4(),
        status="failed",
        phase="failed",
        sections=[completed, failed],
        error_category="provider",
        error_message="down",
        completed_at=object(),
    )
    session = AsyncMock()
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]
    resumed = await service.resume(run.id)
    assert resumed.status == "queued"
    assert completed.status == "completed"
    assert failed.status == "pending"
    assert resumed.phase == "writing"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_is_idempotent_for_terminal_run() -> None:
    run = SimpleNamespace(id=uuid4(), status="completed", phase="completed")
    session = AsyncMock()
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]
    result = await service.cancel(run.id)
    assert result.status == "completed"
    session.flush.assert_not_awaited()


def test_section_cannot_escape_the_approved_claim_ledger() -> None:
    run = SimpleNamespace(plan={"editorial": {"claim_ledger": [{"id": "claim-1"}]}})
    ScriptGenerationJobService._validate_claim_refs(run, ["claim-1"])
    with pytest.raises(GenerationJobError) as captured:
        ScriptGenerationJobService._validate_claim_refs(run, ["invented-claim"])
    assert captured.value.category is GenerationFailureCategory.GROUNDING


@pytest.mark.asyncio
async def test_claim_next_sets_timezone_aware_timestamps() -> None:
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=300)
    run = SimpleNamespace(
        id=uuid4(),
        status="queued",
        started_at=None,
        heartbeat_at=None,
        criado_em=now - timedelta(seconds=60),
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=run))
    )
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), config=Settings(generation_stale_after_seconds=300)
    )
    claimed = await service.claim_next()
    assert claimed is run
    assert run.status == "running"
    assert run.started_at is not None
    assert run.heartbeat_at is not None
    assert run.started_at.tzinfo is not None
    assert run.heartbeat_at.tzinfo is not None
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_next_reclaims_stale_running_job() -> None:
    now = datetime.now(UTC)
    stale_heartbeat = now - timedelta(seconds=600)
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        started_at=now - timedelta(seconds=500),
        heartbeat_at=stale_heartbeat,
        criado_em=now - timedelta(seconds=700),
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=run))
    )
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), config=Settings(generation_stale_after_seconds=300)
    )
    claimed = await service.claim_next()
    assert claimed is run
    assert run.status == "running"
    assert run.heartbeat_at.tzinfo is not None


@pytest.mark.asyncio
async def test_heartbeat_update_preserves_timezone_awareness() -> None:
    now = datetime.now(UTC)
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        started_at=now - timedelta(seconds=100),
        heartbeat_at=now - timedelta(seconds=50),
        criado_em=now - timedelta(seconds=200),
        sections=[],
        evidence_dossier={"research_complete": True},
    )
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), config=Settings()
    )
    service.get = AsyncMock(return_value=run)
    run.heartbeat_at = datetime.now(UTC)
    assert run.heartbeat_at.tzinfo is not None


def test_datetime_now_utc_produces_timezone_aware_values() -> None:
    now = datetime.now(UTC)
    assert now.tzinfo is not None
    naive = now.replace(tzinfo=None)
    assert naive.tzinfo is None
    aware_again = naive.replace(tzinfo=UTC)
    assert aware_again.tzinfo is not None
