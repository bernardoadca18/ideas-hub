"""
Configuração de retry para chamadas externas (LLM, Tavily, APIs).

Usa tenacity para implementar retry com backoff exponencial.
"""
import functools
from typing import Callable, TypeVar, ParamSpec

from tenacity import (
    retry,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
import httpx
import structlog

logger = structlog.get_logger("retry")


# Configuração padrão de retry
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_DELAY_SECONDS = 30
DEFAULT_WAIT_MULTIPLIER = 1
DEFAULT_WAIT_MIN = 1
DEFAULT_WAIT_MAX = 10


def retry_llm(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_delay_seconds: int = DEFAULT_MAX_DELAY_SECONDS,
):
    """
    Decorator de retry para chamadas LLM.

    Retry em caso de:
    - Erros de conexão (httpx.ConnectError)
    - Timeouts (httpx.TimeoutException)
    - Erros 5xx do servidor
    - Rate limits (429)
    """
    return retry(
        stop=(
            stop_after_attempt(max_attempts) |
            stop_after_delay(max_delay_seconds)
        ),
        wait=wait_exponential(
            multiplier=DEFAULT_WAIT_MULTIPLIER,
            min=DEFAULT_WAIT_MIN,
            max=DEFAULT_WAIT_MAX
        ),
        retry=(
            retry_if_exception_type(httpx.ConnectError) |
            retry_if_exception_type(httpx.TimeoutException) |
            retry_if_exception_type(httpx.ReadTimeout) |
            retry_if_exception_type(httpx.ConnectTimeout) |
            retry_if_exception_type(httpx.HTTPStatusError)
        ),
        before_sleep=before_sleep_log(logger, log_level=20),  # INFO
        after=after_log(logger, log_level=20),  # INFO
        reraise=True
    )


def retry_tavily(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_delay_seconds: int = DEFAULT_MAX_DELAY_SECONDS,
):
    """
    Decorator de retry para chamadas Tavily API.

    Retry em caso de:
    - Erros de conexão
    - Timeouts
    - Rate limits
    """
    return retry(
        stop=(
            stop_after_attempt(max_attempts) |
            stop_after_delay(max_delay_seconds)
        ),
        wait=wait_exponential(
            multiplier=DEFAULT_WAIT_MULTIPLIER,
            min=DEFAULT_WAIT_MIN,
            max=DEFAULT_WAIT_MAX
        ),
        retry=(
            retry_if_exception_type(httpx.ConnectError) |
            retry_if_exception_type(httpx.TimeoutException) |
            retry_if_exception_type(httpx.ReadTimeout) |
            retry_if_exception_type(httpx.ConnectTimeout)
        ),
        before_sleep=before_sleep_log(logger, log_level=20),
        after=after_log(logger, log_level=20),
        reraise=True
    )


def retry_api(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_delay_seconds: int = DEFAULT_MAX_DELAY_SECONDS,
):
    """
    Decorator genérico de retry para APIs externas.

    Inclui retry para:
    - Erros de conexão
    - Timeouts
    - Erros HTTP transitórios
    """
    return retry(
        stop=(
            stop_after_attempt(max_attempts) |
            stop_after_delay(max_delay_seconds)
        ),
        wait=wait_exponential(
            multiplier=DEFAULT_WAIT_MULTIPLIER,
            min=DEFAULT_WAIT_MIN,
            max=DEFAULT_WAIT_MAX
        ),
        retry=(
            retry_if_exception_type(httpx.ConnectError) |
            retry_if_exception_type(httpx.TimeoutException) |
            retry_if_exception_type(httpx.ReadTimeout) |
            retry_if_exception_type(httpx.ConnectTimeout) |
            retry_if_exception_type(httpx.HTTPStatusError)
        ),
        before_sleep=before_sleep_log(logger, log_level=20),
        after=after_log(logger, log_level=20),
        reraise=True
    )


# Type hints para decorators
P = ParamSpec('P')
T = TypeVar('T')


def with_retry(
    retry_config: Callable[..., Callable[[Callable[P, T]], Callable[P, T]]] = retry_api,
    **retry_kwargs
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator genérico com configuração de retry customizável.

    Uso:
        @with_retry(retry_llm, max_attempts=5)
        async def call_llm(...):
            ...
    """
    return retry_config(**retry_kwargs)
