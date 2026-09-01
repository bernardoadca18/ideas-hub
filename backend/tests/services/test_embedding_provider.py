from __future__ import annotations

import math
from unittest.mock import AsyncMock

import httpx
import pytest
from app.core.config import Settings
from app.services.embedding_provider import (
    EmbeddingDimensionError,
    EmbeddingRequestError,
    EmbeddingResponseError,
    EmbeddingTransportError,
    OllamaEmbeddingProvider,
    validate_embeddings,
)
from app.services.embeddings import EmbeddingService


def _settings(**overrides) -> Settings:
    return Settings(
        ollama_base_url="http://ollama.test:11434",
        embedding_model="mxbai-embed-large:latest",
        embedding_dim=3,
        embedding_max_attempts=overrides.pop("embedding_max_attempts", 1),
        **overrides,
    )


@pytest.mark.asyncio
async def test_ollama_provider_uses_current_batch_endpoint_without_gateway_auth() -> (
    None
):
    response = httpx.Response(
        200,
        json={
            "model": "mxbai-embed-large:latest",
            "embeddings": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        },
        request=httpx.Request("POST", "http://ollama.test:11434/api/embed"),
    )
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = response
    provider = OllamaEmbeddingProvider(_settings(), client=client)

    vectors = await provider.embed(
        ["primeiro", "segundo"],
        model="mxbai-embed-large:latest",
        expected_dimensions=3,
    )

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    call = client.post.await_args
    assert call.args[0] == "http://ollama.test:11434/api/embed"
    assert call.kwargs["json"] == {
        "model": "mxbai-embed-large:latest",
        "input": ["primeiro", "segundo"],
    }
    assert "headers" not in call.kwargs


@pytest.mark.asyncio
async def test_ollama_dimension_mismatch_and_ordinary_400_are_terminal() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    provider = OllamaEmbeddingProvider(_settings(), client=client)
    client.post.return_value = httpx.Response(
        200,
        json={"embeddings": [[1.0, 2.0]]},
        request=httpx.Request("POST", "http://ollama.test:11434/api/embed"),
    )
    with pytest.raises(EmbeddingDimensionError, match="2 dimensions; expected 3"):
        await provider.embed(
            ["texto"], model="mxbai-embed-large:latest", expected_dimensions=3
        )
    assert client.post.await_count == 1

    client.reset_mock()
    client.post.return_value = httpx.Response(
        400,
        request=httpx.Request("POST", "http://ollama.test:11434/api/embed"),
    )
    with pytest.raises(EmbeddingRequestError, match="HTTP 400"):
        await provider.embed(
            ["texto"], model="mxbai-embed-large:latest", expected_dimensions=3
        )
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_ollama_transient_retry_is_bounded(monkeypatch) -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = [
        httpx.Response(
            503,
            request=httpx.Request("POST", "http://ollama.test:11434/api/embed"),
        ),
        httpx.Response(
            503,
            request=httpx.Request("POST", "http://ollama.test:11434/api/embed"),
        ),
    ]
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.embedding_provider.asyncio.sleep", sleep)
    provider = OllamaEmbeddingProvider(
        _settings(embedding_max_attempts=2), client=client
    )

    with pytest.raises(EmbeddingTransportError):
        await provider.embed(
            ["texto"], model="mxbai-embed-large:latest", expected_dimensions=3
        )

    assert client.post.await_count == 2
    sleep.assert_awaited_once_with(1)


def test_embedding_validation_rejects_count_and_non_finite_values() -> None:
    with pytest.raises(EmbeddingResponseError, match="1 vectors for 2 inputs"):
        validate_embeddings([[1.0]], expected_count=2, expected_dimensions=1)
    with pytest.raises(EmbeddingResponseError, match="non-finite"):
        validate_embeddings([[math.inf, 0.0]], expected_count=1, expected_dimensions=2)


@pytest.mark.asyncio
async def test_embedding_service_delegates_to_ollama_provider() -> None:
    provider = AsyncMock()
    provider.embed.return_value = [[1.0, 0.0, 0.0]]
    service = EmbeddingService(provider, model="local-model", dimensions=3)

    vector = await service.generate_for_ideia("Título", "Descrição")

    assert vector == [1.0, 0.0, 0.0]
    provider.embed.assert_awaited_once_with(
        ["Título\n\nDescrição"],
        model="local-model",
        expected_dimensions=3,
    )
