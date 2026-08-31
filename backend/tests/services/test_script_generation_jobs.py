from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.schemas.generation import (
    EditorialPlanOutput,
    GlobalEditorialPlanOutput,
    PlannedSectionBatchOutput,
)
from app.services.llm_gateway import (
    LLMCallResult,
    LLMFailureCategory,
    LLMGatewayError,
    LLMTaskRole,
)
from app.services.script_generation_jobs import (
    GenerationFailureCategory,
    GenerationJobError,
    ScriptGenerationJobService,
    _global_plan_output_contract,
    _planning_max_tokens,
    _repair_max_tokens,
    _section_batch_output_contract,
    _section_batches,
    _temperature_for_role,
)


def _config() -> Settings:
    return Settings(
        llm_model="standard-route",
        llm_fast_model="fast-route",
        llm_standard_model="standard-route",
        llm_strong_model="strong-route",
    )


def _result(
    content: str,
    *,
    role: LLMTaskRole = LLMTaskRole.PLANNING,
    finish_reason: str = "stop",
    max_tokens: int = 3000,
    completion_tokens: int = 300,
) -> LLMCallResult:
    return LLMCallResult(
        content=content,
        task_role=role.value,
        model_alias="standard-route"
        if role is not LLMTaskRole.REPAIR
        else "fast-route",
        actual_model="provider/model",
        provider="test",
        prompt_identity="prompt",
        temperature=0.0 if role is LLMTaskRole.REPAIR else 0.5,
        max_tokens=max_tokens,
        prompt_tokens=100,
        completion_tokens=completion_tokens,
        total_tokens=100 + completion_tokens,
        latency_seconds=0.01,
        attempt_count=1,
        finish_reason=finish_reason,
    )


def _budgets(count: int, *, chapter_count: int = 1) -> list[dict[str, int | str]]:
    return [
        {
            "key": f"section-{index + 1:03d}",
            "order": index,
            "chapter_order": min(chapter_count - 1, index * chapter_count // count),
            "target_duration_seconds": 240,
            "target_words": 596,
            "min_words": 507,
            "max_words": 685,
        }
        for index in range(count)
    ]


def _global_json(*, chapter_count: int = 1) -> str:
    return json.dumps(
        {
            "thesis": "Uma tese editorial verificável.",
            "audience_promise": "Entender o argumento sem fatos inventados.",
            "chapters": [
                {
                    "key": f"chapter-{index + 1:03d}",
                    "title": f"Capítulo {index + 1}",
                    "purpose": "Organizar a progressão editorial.",
                }
                for index in range(chapter_count)
            ],
            "open_loops": [],
        }
    )


def _section_dict(key: str) -> dict[str, object]:
    return {
        "key": key,
        "title": f"Plano {key}",
        "purpose": "Desenvolver o argumento com clareza.",
        "narrative_role": "desenvolvimento",
        "beats": ["Apresentar o ponto central"],
        "evidence_refs": [],
        "must_cover": ["A tese editorial"],
        "must_not_repeat": [],
        "transition_target": "Conectar com a próxima seção",
    }


def _batch_json(keys: list[str]) -> str:
    return json.dumps({"sections": [_section_dict(key) for key in keys]})


def _planning_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    section_count: int = 3,
    chapter_count: int = 1,
) -> tuple[
    ScriptGenerationJobService, AsyncMock, SimpleNamespace, list[SimpleNamespace]
]:
    rows: list[SimpleNamespace] = []
    session = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.side_effect = lambda: rows
    session.execute = AsyncMock(return_value=scalar_result)
    session.add = MagicMock(side_effect=rows.append)
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        phase="queued",
        status="running",
        plan={
            "sections": _budgets(section_count, chapter_count=chapter_count),
            "chapter_count": chapter_count,
        },
        sections=rows,
        evidence_dossier={
            "sources": [{"id": "idea-description"}],
            "fragments": [],
            "claims": [],
        },
        call_usage={
            "calls": 0,
            "total_tokens": 0,
            "fallbacks": [],
            "escalations": [],
        },
        model_policy={"strategy": "standard"},
        strategy_identity="fragmented-planning-test",
        heartbeat_at=None,
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                titulo="Fixture editorial",
                descricao_breve="Conteúdo sintético sem fatos externos.",
                author_briefing=None,
            )
        ),
    )
    return service, session, run, rows


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
    gateway.complete.side_effect = lambda **kwargs: _result(
        "{}", role=role, max_tokens=kwargs["max_tokens"]
    )
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
    assert gateway.complete.await_args.kwargs["temperature"] == _temperature_for_role(
        role
    )
    assert run.call_usage["calls"] == 1
    assert run.call_usage["by_role"] == {role.value: 1}
    assert run.call_usage["finish_reasons"][0]["role"] == role.value
    assert (len(run.call_usage["escalations"]) == 1) is bool(escalation)


@pytest.mark.asyncio
async def test_valid_global_fragment_does_not_call_repair() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._complete = AsyncMock()  # type: ignore[method-assign]
    result = _result(_global_json())
    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(), result, GlobalEditorialPlanOutput
    )
    assert parsed.thesis.startswith("Uma tese")
    assert provenance == result.provenance()
    service._complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_wrong_root_uses_global_only_repair() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    invalid = _result(json.dumps({"chapter-001": {"title": "Capítulo"}}))
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(_global_json(), role=LLMTaskRole.REPAIR)
    )
    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(),
        invalid,
        GlobalEditorialPlanOutput,
        repair_contract=_global_plan_output_contract(["chapter-001"]),
    )
    assert parsed.chapters[0].key == "chapter-001"
    assert provenance["repair_reason"] == "ValidationError"
    prompt = service._complete.await_args.kwargs["prompt"]
    assert "VALIDATION ERRORS" in prompt
    assert "Do not return sections" in prompt
    assert "IMMUTABLE BATCH SKELETON" not in prompt


@pytest.mark.asyncio
async def test_section_wrong_root_repairs_only_that_batch() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    keys = ["section-001", "section-002"]
    invalid = _result(json.dumps({key: _section_dict(key) for key in keys}))
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(_batch_json(keys), role=LLMTaskRole.REPAIR)
    )
    parsed, _ = await service._parse_or_repair(
        SimpleNamespace(),
        invalid,
        PlannedSectionBatchOutput,
        repair_contract=_section_batch_output_contract(keys),
    )
    assert [section.key for section in parsed.sections] == keys
    prompt = service._complete.await_args.kwargs["prompt"]
    assert "section-001" in prompt and "section-002" in prompt
    assert "GLOBAL THESIS" not in prompt
    assert "audience_promise" not in prompt
    assert "EditorialPlanOutput" not in prompt


@pytest.mark.asyncio
async def test_fragment_repair_is_bounded_and_truncation_is_terminal() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            "{",
            role=LLMTaskRole.REPAIR,
            finish_reason="length",
            max_tokens=2500,
            completion_tokens=2490,
        )
    )
    with pytest.raises(LLMGatewayError) as captured:
        await service._parse_or_repair(
            SimpleNamespace(), _result("{"), PlannedSectionBatchOutput
        )
    assert captured.value.category is LLMFailureCategory.FORMAT
    service._complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_three_sections_assemble_exact_host_owned_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, rows = _planning_fixture(monkeypatch)
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_global_json(), max_tokens=2500),
            _result(
                _batch_json(["section-001", "section-002", "section-003"]),
                max_tokens=4000,
            ),
        ]
    )
    await service._plan(run)
    canonical = EditorialPlanOutput.model_validate(run.plan["editorial"])
    assert [section.key for section in canonical.sections] == [
        "section-001",
        "section-002",
        "section-003",
    ]
    assert run.phase == "writing"
    assert run.plan["planning_state"]["status"] == "completed"
    assert len(run.plan["planning_state"]["accepted_batches"]) == 1
    assert [row.status for row in rows] == ["pending", "pending", "pending"]
    assert [row.section_plan["target_words"] for row in rows] == [596, 596, 596]
    schemas = [call.kwargs["schema"] for call in service._complete.await_args_list]
    assert schemas == [
        GlobalEditorialPlanOutput.model_json_schema(),
        PlannedSectionBatchOutput.model_json_schema(),
    ]
    assert EditorialPlanOutput.model_json_schema() not in schemas


@pytest.mark.asyncio
async def test_wrong_section_batch_root_repairs_only_batch_in_real_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, _ = _planning_fixture(monkeypatch)
    keyed_root = json.dumps(
        {
            key: _section_dict(key)
            for key in ["section-001", "section-002", "section-003"]
        }
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_global_json()),
            _result(keyed_root, completion_tokens=900),
            _result(
                _batch_json(["section-001", "section-002", "section-003"]),
                role=LLMTaskRole.REPAIR,
            ),
        ]
    )
    await service._plan(run)
    assert run.phase == "writing"
    roles = [call.kwargs["role"] for call in service._complete.await_args_list]
    assert roles == [LLMTaskRole.PLANNING, LLMTaskRole.PLANNING, LLMTaskRole.REPAIR]
    repair_prompt = service._complete.await_args_list[2].kwargs["prompt"]
    assert "section-001" in repair_prompt
    assert "Uma tese editorial verificável" not in repair_prompt
    assert "claim_ledger" not in repair_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actual_keys",
    [
        ["section-001", "section-002", "section-003", "section-004"],
        ["section-001", "section-002"],
        ["section-001", "wrong-key", "section-003"],
        ["section-002", "section-001", "section-003"],
    ],
    ids=["extra", "missing", "wrong", "reordered"],
)
async def test_section_batch_contract_mismatch_is_rejected_locally(
    monkeypatch: pytest.MonkeyPatch, actual_keys: list[str]
) -> None:
    service, _, run, rows = _planning_fixture(monkeypatch)
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_result(_global_json()), _result(_batch_json(actual_keys))]
    )
    with pytest.raises(GenerationJobError) as captured:
        await service._plan(run)
    assert captured.value.category is GenerationFailureCategory.SCHEMA
    assert "section planning batch contract mismatch" in str(captured.value)
    assert all(row.status == "planning" for row in rows)


@pytest.mark.asyncio
async def test_truncated_multi_section_batch_splits_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, _ = _planning_fixture(monkeypatch)
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_global_json()),
            _result(
                "{", finish_reason="length", max_tokens=4000, completion_tokens=3990
            ),
            _result(_batch_json(["section-001"])),
            _result(_batch_json(["section-002", "section-003"])),
        ]
    )
    await service._plan(run)
    state = run.plan["planning_state"]
    assert len(state["truncated_batches"]) == 1
    assert len(state["accepted_batches"]) == 2
    assert [section["key"] for section in run.plan["editorial"]["sections"]] == [
        "section-001",
        "section-002",
        "section-003",
    ]


@pytest.mark.asyncio
async def test_singleton_batch_truncation_is_terminal_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, rows = _planning_fixture(monkeypatch, section_count=1)
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_global_json()),
            _result(
                "{", finish_reason="length", max_tokens=3000, completion_tokens=2990
            ),
        ]
    )
    with pytest.raises(LLMGatewayError) as captured:
        await service._plan(run)
    assert captured.value.category is LLMFailureCategory.FORMAT
    assert "finish_reason=length" in str(captured.value)
    assert rows[0].status == "planning"


@pytest.mark.asyncio
async def test_resume_reuses_global_and_completed_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, rows = _planning_fixture(monkeypatch)
    for budget in run.plan["sections"]:
        key = str(budget["key"])
        completed = key != "section-003"
        rows.append(
            SimpleNamespace(
                run_id=run.id,
                section_key=key,
                section_order=budget["order"],
                chapter_order=budget["chapter_order"],
                status="pending" if completed else "planning",
                section_plan={
                    **budget,
                    **(_section_dict(key) if completed else {}),
                    "planning_status": "completed" if completed else "pending",
                },
                prompt_provenance={"already_completed": True} if completed else None,
            )
        )
    run.plan["planning_state"] = {
        "version": "fragmented_editorial_planning_v1",
        "status": "planning",
        "global_output": json.loads(_global_json()),
        "global_provenance": {"persisted": True},
        "accepted_batches": [{"expected_section_keys": ["section-001", "section-002"]}],
        "truncated_batches": [],
    }
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(_batch_json(["section-003"]))
    )
    await service._plan(run)
    service._complete.assert_awaited_once()
    assert service._complete.await_args.kwargs["role"] is LLMTaskRole.PLANNING
    assert [row.section_plan["title"] for row in rows[:2]] == [
        "Plano section-001",
        "Plano section-002",
    ]
    assert len(run.plan["planning_state"]["accepted_batches"]) == 2


def test_long_form_batches_are_bounded_for_13_and_28_sections() -> None:
    batches_13 = _section_batches(_budgets(13, chapter_count=3))
    batches_28 = _section_batches(_budgets(28, chapter_count=5))
    assert [len(batch) for batch in batches_13] == [4, 4, 4, 1]
    assert [len(batch) for batch in batches_28] == [4, 4, 4, 4, 4, 4, 4]
    assert max(map(len, [*batches_13, *batches_28])) == 4


@pytest.mark.asyncio
async def test_28_sections_never_request_monolithic_editorial_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, _ = _planning_fixture(
        monkeypatch, section_count=28, chapter_count=5
    )
    results = [_result(_global_json(chapter_count=5))]
    results.extend(
        _result(_batch_json([str(item["key"]) for item in batch]))
        for batch in _section_batches(run.plan["sections"])
    )
    service._complete = AsyncMock(side_effect=results)  # type: ignore[method-assign]
    await service._plan(run)
    assert service._complete.await_count == 8
    schemas = [call.kwargs["schema"] for call in service._complete.await_args_list]
    assert schemas[0] == GlobalEditorialPlanOutput.model_json_schema()
    assert all(
        schema == PlannedSectionBatchOutput.model_json_schema()
        for schema in schemas[1:]
    )
    assert EditorialPlanOutput.model_json_schema() not in schemas
    assert len(run.plan["editorial"]["sections"]) == 28


def test_planning_and_repair_token_budgets_remain_bounded() -> None:
    assert _planning_max_tokens(1) == 3000
    assert _planning_max_tokens(4) == 5000
    with pytest.raises(ValueError, match="at least one"):
        _planning_max_tokens(0)
    assert (
        _repair_max_tokens(_result("{}", completion_tokens=1519, max_tokens=4000))
        == 3519
    )
    assert (
        _repair_max_tokens(_result("{}", completion_tokens=5000, max_tokens=6000))
        == 6000
    )


def test_task_temperature_policy_keeps_repair_deterministic() -> None:
    assert _temperature_for_role(LLMTaskRole.REPAIR) == 0.0
    assert _temperature_for_role(LLMTaskRole.PLANNING) == 0.5
    assert _temperature_for_role(LLMTaskRole.WRITING) == 0.7


@pytest.mark.asyncio
async def test_process_refreshes_new_planning_rows_before_writing() -> None:
    section = SimpleNamespace(status="pending")
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        phase="planning",
        sections=[],
        plan={"sections": [], "chapter_count": 1},
        evidence_dossier={"research_complete": True},
        completed_sections=0,
        heartbeat_at=None,
        completed_at=None,
        roteiro_id=None,
    )
    session = AsyncMock()

    async def refresh(target, *, attribute_names):
        if attribute_names == ["sections"]:
            target.sections = [section]

    session.refresh.side_effect = refresh
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]

    async def complete_plan(target):
        target.plan = {
            **target.plan,
            "editorial": {},
            "planning_state": {
                "version": "fragmented_editorial_planning_v1",
                "status": "completed",
            },
        }

    async def write_section(_run, target):
        target.status = "completed"

    service._plan = AsyncMock(side_effect=complete_plan)  # type: ignore[method-assign]
    service._write_section = AsyncMock(side_effect=write_section)  # type: ignore[method-assign]
    service._assemble = AsyncMock()  # type: ignore[method-assign]

    result = await service.process(run.id)

    assert result.status == "completed"
    service._write_section.assert_awaited_once_with(run, section)
    assert any(
        call.kwargs.get("attribute_names") == ["sections"]
        for call in session.refresh.await_args_list
    )


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
        plan={
            "editorial": {},
            "planning_state": {
                "version": "fragmented_editorial_planning_v1",
                "status": "completed",
            },
        },
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
    session.refresh.assert_awaited_once_with(run)


@pytest.mark.asyncio
async def test_resume_incomplete_fragmented_plan_returns_to_planning() -> None:
    planning = SimpleNamespace(
        status="planning", error_category=None, error_message=None
    )
    run = SimpleNamespace(
        id=uuid4(),
        status="failed",
        phase="failed",
        sections=[planning],
        plan={
            "planning_state": {
                "version": "fragmented_editorial_planning_v1",
                "status": "planning",
            }
        },
        error_category="provider",
        error_message="down",
        completed_at=object(),
    )
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]
    resumed = await service.resume(run.id)
    assert resumed.phase == "planning"


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
        session,
        gateway=AsyncMock(),
        config=Settings(generation_stale_after_seconds=300),
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
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        started_at=now - timedelta(seconds=500),
        heartbeat_at=now - timedelta(seconds=600),
        criado_em=now - timedelta(seconds=700),
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=run))
    )
    service = ScriptGenerationJobService(
        session,
        gateway=AsyncMock(),
        config=Settings(generation_stale_after_seconds=300),
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
