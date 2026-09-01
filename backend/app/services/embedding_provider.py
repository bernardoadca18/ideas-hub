"""Pooled direct Ollama boundary for Ideas Hub embeddings."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from app.core.config import Settings, settings


class EmbeddingProviderError(RuntimeError):
    """Base error for direct embedding failures."""


class EmbeddingTransportError(EmbeddingProviderError):
    """Ollama remained unavailable after bounded transient retries."""


class EmbeddingRequestError(EmbeddingProviderError):
    """Ollama rejected a non-retryable embedding request."""


class EmbeddingResponseError(EmbeddingProviderError):
    """Ollama returned a malformed or incomplete response."""


class EmbeddingDimensionError(EmbeddingProviderError, ValueError):
    """An embedding does not match the persisted pgvector dimension."""


class EmbeddingProvider(Protocol):
    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        expected_dimensions: int,
    ) -> list[list[float]]: ...


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 429} or 500 <= status_code <= 599


def validate_embeddings(
    embeddings: Sequence[Sequence[float]],
    *,
    expected_count: int,
    expected_dimensions: int,
) -> list[list[float]]:
    if len(embeddings) != expected_count:
        raise EmbeddingResponseError(
            f"Ollama returned {len(embeddings)} vectors for {expected_count} inputs"
        )
    validated: list[list[float]] = []
    for vector in embeddings:
        if len(vector) != expected_dimensions:
            raise EmbeddingDimensionError(
                f"embedding has {len(vector)} dimensions; expected {expected_dimensions}"
            )
        values = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in values):
            raise EmbeddingResponseError("Ollama embedding contains a non-finite value")
        validated.append(values)
    return validated


class OllamaEmbeddingProvider:
    """One direct Ollama connection pool per process, without model fallback."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=self.config.embedding_connect_timeout_seconds,
                    read=self.config.embedding_timeout_seconds,
                    write=30.0,
                    pool=10.0,
                ),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        expected_dimensions: int,
    ) -> list[list[float]]:
        inputs = list(texts)
        if not inputs:
            return []
        last_error: Exception | None = None
        for attempt in range(1, self.config.embedding_max_attempts + 1):
            try:
                response = await self._get_client().post(
                    f"{self.config.ollama_base_url}/api/embed",
                    json={"model": model, "input": inputs},
                )
                if response.status_code >= 400:
                    if not _is_retryable_status(response.status_code):
                        raise EmbeddingRequestError(
                            f"Ollama rejected embedding request with HTTP {response.status_code}"
                        )
                    response.raise_for_status()
                payload: Any = response.json()
                vectors = payload["embeddings"]
                if not isinstance(vectors, list) or not all(
                    isinstance(vector, list) for vector in vectors
                ):
                    raise EmbeddingResponseError(
                        "Ollama returned an invalid embeddings response"
                    )
                return validate_embeddings(
                    vectors,
                    expected_count=len(inputs),
                    expected_dimensions=expected_dimensions,
                )
            except EmbeddingProviderError:
                raise
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise EmbeddingResponseError(
                    "Ollama returned a malformed embeddings response"
                ) from exc
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.HTTPStatusError,
            ) as exc:
                last_error = exc
                if attempt >= self.config.embedding_max_attempts:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise EmbeddingTransportError(
            "Ollama remained unavailable after bounded embedding retries"
        ) from last_error


ollama_embedding_provider = OllamaEmbeddingProvider()
