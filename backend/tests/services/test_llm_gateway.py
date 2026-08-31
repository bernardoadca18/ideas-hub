from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from app.core.config import Settings
from app.services.llm_gateway import (
    LLMFailureCategory,
    LLMGateway,
    LLMGatewayError,
    LLMTaskRole,
)


def _settings(*, attempts: int = 3) -> Settings:
    return Settings(
        litellm_base_url="http://litellm.test",
        llm_model="standard-alias",
        llm_fast_model="fast-alias",
        llm_strong_model="strong-alias",
        llm_max_attempts=attempts,
    )


def _success(*, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "provider/model",
            "choices": [
                {
                    "message": {"content": '{"ok":true}'},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 3,
                "completion_tokens_details": {"reasoning_tokens": 1},
                "total_tokens": 5,
            },
        },
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 422])
async def test_non_transient_status_is_not_retried(status: int) -> None:
    response = httpx.Response(
        status,
        text="rejected",
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = response
    gateway = LLMGateway(_settings(), client=client)
    with pytest.raises(LLMGatewayError) as captured:
        await gateway.complete(
            messages=[{"role": "user", "content": "test"}],
            role=LLMTaskRole.WRITING,
            temperature=0.7,
            max_tokens=100,
        )
    assert client.post.await_count == 1
    expected = (
        LLMFailureCategory.AUTH if status in {401, 403} else LLMFailureCategory.REQUEST
    )
    assert captured.value.category is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 503])
async def test_transient_status_is_retried(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = httpx.Response(
        status,
        text="temporary",
        headers={"Retry-After": "0"},
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = [failure, _success()]
    monkeypatch.setattr("app.services.llm_gateway.asyncio.sleep", AsyncMock())
    result = await LLMGateway(_settings(), client=client).complete(
        messages=[{"role": "user", "content": "test"}],
        role=LLMTaskRole.WRITING,
        temperature=0.7,
        max_tokens=100,
    )
    assert result.content == '{"ok":true}'
    assert result.attempt_count == 2


@pytest.mark.asyncio
async def test_finish_reason_is_exposed_in_result_and_provenance() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _success(finish_reason="length")

    result = await LLMGateway(_settings(), client=client).complete(
        messages=[{"role": "user", "content": "test"}],
        role=LLMTaskRole.PLANNING,
        temperature=0.5,
        max_tokens=100,
    )

    assert result.finish_reason == "length"
    assert result.provenance()["finish_reason"] == "length"


@pytest.mark.asyncio
async def test_reasoning_usage_and_visible_size_are_recorded() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _success()

    result = await LLMGateway(_settings(), client=client).complete(
        messages=[{"role": "user", "content": "test"}],
        role=LLMTaskRole.WRITING,
        temperature=0.7,
        max_tokens=3000,
    )

    assert result.reasoning_tokens == 1
    assert result.visible_output_characters == len('{"ok":true}')
    assert result.provenance()["usage"]["reasoning_tokens"] == 1


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_classified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = httpx.ReadTimeout("slow")
    monkeypatch.setattr("app.services.llm_gateway.asyncio.sleep", AsyncMock())
    with pytest.raises(LLMGatewayError) as captured:
        await LLMGateway(_settings(attempts=2), client=client).complete(
            messages=[{"role": "user", "content": "test"}],
            role=LLMTaskRole.PLANNING,
            temperature=0.5,
            max_tokens=100,
        )
    assert client.post.await_count == 2
    assert captured.value.category is LLMFailureCategory.TRANSPORT


@pytest.mark.asyncio
async def test_native_schema_falls_back_only_when_provider_rejects_feature() -> None:
    unsupported = httpx.Response(
        400,
        text="response_format json_schema unsupported",
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = [unsupported, _success()]
    result = await LLMGateway(_settings(), client=client).complete(
        messages=[{"role": "user", "content": "test"}],
        role=LLMTaskRole.FAST,
        temperature=0,
        max_tokens=100,
        response_schema={"type": "object"},
    )
    assert result.fallback_reason == "provider_json_schema_unsupported"
    first_call = client.post.await_args_list[0].kwargs["json"]
    assert first_call["response_format"]["type"] == "json_schema"
    second_call = client.post.await_args_list[1].kwargs["json"]
    assert second_call["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_json_schema_fallback_for_gemini_invalid_argument() -> None:
    gemini_error = httpx.Response(
        400,
        text='{"error":{"message":"litellm.BadRequestError: VertexAIException BadRequestError - {\\"error\\": {\\"code\\": 400, \\"message\\": \\"Request contains an invalid argument.\\", \\"status\\": \\"INVALID_ARGUMENT\\"}}}\'',
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = [gemini_error, _success()]
    result = await LLMGateway(_settings(), client=client).complete(
        messages=[{"role": "user", "content": "test"}],
        role=LLMTaskRole.PLANNING,
        temperature=0.5,
        max_tokens=1000,
        response_schema={
            "type": "object",
            "properties": {"thesis": {"type": "string"}},
        },
    )
    assert result.fallback_reason == "provider_json_schema_unsupported"
    assert result.content == '{"ok":true}'
    assert client.post.await_count == 2
    second_call_payload = client.post.await_args_list[1].kwargs["json"]
    assert second_call_payload.get("response_format") == {"type": "json_object"}


@pytest.mark.asyncio
async def test_json_schema_rejected_without_schema_returns_error() -> None:
    gemini_error = httpx.Response(
        400,
        text="Request contains an invalid argument",
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = gemini_error
    with pytest.raises(LLMGatewayError) as captured:
        await LLMGateway(_settings(), client=client).complete(
            messages=[{"role": "user", "content": "test"}],
            role=LLMTaskRole.WRITING,
            temperature=0.7,
            max_tokens=100,
        )
    assert captured.value.category is LLMFailureCategory.REQUEST
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_regular_400_with_schema_does_not_use_capability_fallback() -> None:
    rejected = httpx.Response(
        400,
        text="request rejected because the input is too large",
        request=httpx.Request("POST", "http://litellm.test/v1/chat/completions"),
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = rejected
    with pytest.raises(LLMGatewayError) as captured:
        await LLMGateway(_settings(), client=client).complete(
            messages=[{"role": "user", "content": "test"}],
            role=LLMTaskRole.PLANNING,
            temperature=0.5,
            max_tokens=100,
            response_schema={"type": "object"},
        )
    assert captured.value.category is LLMFailureCategory.REQUEST
    assert client.post.await_count == 1
