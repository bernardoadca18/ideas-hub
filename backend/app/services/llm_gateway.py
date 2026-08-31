"""Provider-neutral, pooled LiteLLM gateway with bounded retry and call provenance."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
import structlog

from app.core.config import Settings, settings

logger = structlog.get_logger("services.llm_gateway")


class LLMTaskRole(StrEnum):
    FAST = "fast"
    PLANNING = "planning"
    WRITING = "writing"
    CRITIC = "critic"
    REPAIR = "repair"


class LLMFailureCategory(StrEnum):
    TRANSPORT = "transport_failure"
    RATE_LIMIT = "rate_limit"
    AUTH = "authentication_failure"
    REQUEST = "request_failure"
    PROVIDER = "provider_failure"
    FORMAT = "format_failure"


class LLMGatewayError(RuntimeError):
    def __init__(
        self,
        category: LLMFailureCategory,
        message: str,
        *,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.status_code = status_code


@dataclass(frozen=True)
class LLMCallResult:
    content: str
    task_role: str
    model_alias: str
    actual_model: str | None
    provider: str | None
    prompt_identity: str | None
    temperature: float
    max_tokens: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_seconds: float
    attempt_count: int
    fallback_reason: str | None = None
    escalation_reason: str | None = None

    def provenance(self) -> dict[str, Any]:
        return {
            "task_role": self.task_role,
            "model_alias": self.model_alias,
            "actual_model": self.actual_model,
            "provider": self.provider,
            "prompt_identity": self.prompt_identity,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
            },
            "latency_seconds": self.latency_seconds,
            "attempt_count": self.attempt_count,
            "fallback_reason": self.fallback_reason,
            "escalation_reason": self.escalation_reason,
        }


def is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 429} or 500 <= status_code <= 599


def _is_structured_output_rejection(response: httpx.Response) -> bool:
    text = response.text.casefold()
    return any(
        token in text
        for token in (
            "response_format",
            "json_schema",
            "invalid_argument",
            "unsupported_parameter",
            "structured_output",
        )
    )


class LLMGateway:
    """One connection pool per process; callers retain deterministic task policy."""

    def __init__(
        self, config: Settings = settings, *, client: httpx.AsyncClient | None = None
    ):
        self.config = config
        self._client = client
        self._owns_client = client is None

    def model_for(self, role: LLMTaskRole) -> str:
        if role in {LLMTaskRole.FAST, LLMTaskRole.REPAIR}:
            return self.config.resolved_llm_fast_model
        if role in {LLMTaskRole.PLANNING, LLMTaskRole.CRITIC}:
            return self.config.resolved_llm_standard_model
        return self.config.resolved_llm_standard_model

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=self.config.llm_connect_timeout_seconds,
                read=self.config.llm_read_timeout_seconds,
                write=30.0,
                pool=10.0,
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        role: LLMTaskRole,
        temperature: float,
        max_tokens: int,
        prompt_identity: str | None = None,
        response_schema: dict[str, Any] | None = None,
        model_alias: str | None = None,
        fallback_reason: str | None = None,
        escalation_reason: str | None = None,
    ) -> LLMCallResult:
        if (
            sum(len(item.get("content", "")) for item in messages)
            > self.config.llm_max_input_chars
        ):
            raise LLMGatewayError(
                LLMFailureCategory.REQUEST,
                "LLM input exceeds configured context budget",
            )
        model = model_alias or self.model_for(role)
        if not model:
            raise LLMGatewayError(
                LLMFailureCategory.REQUEST, "LLM model route is not configured"
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": f"{role.value}_output",
                    "strict": True,
                    "schema": response_schema,
                },
            }
        started = time.monotonic()
        last_error: Exception | None = None
        structured_fallback_used = False
        for attempt in range(1, self.config.llm_max_attempts + 1):
            try:
                response = await self._get_client().post(
                    f"{self.config.litellm_base_url.rstrip('/')}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.config.litellm_master_key or 'dummy-key'}"
                    },
                    # Keep each attempt immutable for transport observability/tests;
                    # structured-output fallback mutates only the next attempt.
                    json=dict(payload),
                )
                if (
                    response.status_code == 400
                    and response_schema is not None
                    and not structured_fallback_used
                    and _is_structured_output_rejection(response)
                ):
                    logger.debug(
                        "llm_json_schema_fallback",
                        task_role=role.value,
                        model_alias=model,
                        status_code=400,
                        prompt_identity=prompt_identity,
                    )
                    payload["response_format"] = {"type": "json_object"}
                    structured_fallback_used = True
                    fallback_reason = "provider_json_schema_unsupported"
                    continue
                if response.status_code >= 400:
                    if not is_retryable_status(response.status_code):
                        category = (
                            LLMFailureCategory.AUTH
                            if response.status_code in {401, 403}
                            else LLMFailureCategory.REQUEST
                        )
                        logger.warning(
                            "llm_request_rejected",
                            task_role=role.value,
                            model_alias=model,
                            status_code=response.status_code,
                            category=category.value,
                            prompt_identity=prompt_identity,
                        )
                        raise LLMGatewayError(
                            category,
                            "LLM request was rejected",
                            status_code=response.status_code,
                        )
                    response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]["message"]["content"]
                if not isinstance(choice, str) or not choice.strip():
                    raise LLMGatewayError(
                        LLMFailureCategory.FORMAT, "LLM returned empty content"
                    )
                usage = data.get("usage") or {}
                result = LLMCallResult(
                    content=choice,
                    task_role=role.value,
                    model_alias=model,
                    actual_model=data.get("model"),
                    provider=data.get("provider"),
                    prompt_identity=prompt_identity,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                    latency_seconds=round(time.monotonic() - started, 3),
                    attempt_count=attempt,
                    fallback_reason=fallback_reason,
                    escalation_reason=escalation_reason,
                )
                logger.info("llm_call_completed", **result.provenance())
                return result
            except LLMGatewayError:
                raise
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise LLMGatewayError(
                    LLMFailureCategory.FORMAT,
                    "LLM provider returned a malformed response envelope",
                ) from exc
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.HTTPStatusError,
            ) as exc:
                last_error = exc
                status = (
                    exc.response.status_code
                    if isinstance(exc, httpx.HTTPStatusError)
                    else None
                )
                if status is not None and not is_retryable_status(status):
                    raise LLMGatewayError(
                        LLMFailureCategory.REQUEST,
                        "LLM request failed",
                        status_code=status,
                    ) from exc
                if attempt >= self.config.llm_max_attempts:
                    break
                retry_after = 0.0
                if isinstance(exc, httpx.HTTPStatusError):
                    raw = exc.response.headers.get("Retry-After")
                    try:
                        retry_after = min(float(raw), 30.0) if raw else 0.0
                    except ValueError:
                        retry_after = 0.0
                await asyncio.sleep(max(retry_after, min(2 ** (attempt - 1), 8)))
        category = (
            LLMFailureCategory.RATE_LIMIT
            if isinstance(last_error, httpx.HTTPStatusError)
            and last_error.response.status_code == 429
            else LLMFailureCategory.TRANSPORT
        )
        raise LLMGatewayError(
            category, "LLM provider remained unavailable after bounded retries"
        ) from last_error


llm_gateway = LLMGateway()
