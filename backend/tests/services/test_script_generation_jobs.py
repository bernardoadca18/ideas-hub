from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.services.llm_gateway import LLMCallResult, LLMTaskRole
from app.services.script_generation_jobs import (
    GenerationFailureCategory,
    GenerationJobError,
    ScriptGenerationJobService,
)


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
