from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from app.core.config import Settings
from app.services.external_research import ExternalResearchClient


def _settings() -> Settings:
    return Settings(
        tavily_api_key="test-key",
        tavily_max_attempts=2,
        llm_standard_model="test-model",
    )


@pytest.mark.asyncio
async def test_research_dedicated_boundary_returns_bounded_untrusted_sources() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = httpx.Response(
        200,
        json={
            "results": [
                {
                    "title": "Official trailer",
                    "url": "https://example.test/a",
                    "content": "observed material",
                },
                {"title": "Empty", "url": "https://example.test/empty", "content": ""},
            ]
        },
        request=httpx.Request("POST", "https://api.tavily.com/search"),
    )
    sources = await ExternalResearchClient(_settings(), client=client).search(
        "GTA trailer",
        max_results=5,
    )
    assert len(sources) == 1
    assert sources[0].snippet == "observed material"
    assert sources[0].query == "GTA trailer"
    assert sources[0].domain == "example.test"
    assert "test-key" not in sources[0].to_dict().values()

    second = await ExternalResearchClient(_settings(), client=client).search(
        "different query",
        max_results=5,
    )
    assert second[0].source_id == sources[0].source_id


@pytest.mark.asyncio
async def test_research_passes_a_bounded_deduplicated_domain_hint() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = httpx.Response(
        200,
        json={"results": []},
        request=httpx.Request("POST", "https://api.tavily.com/search"),
    )

    await ExternalResearchClient(_settings(), client=client).search(
        "GTA VI",
        max_results=3,
        include_domains=("RockstarGames.com", "www.ign.com", "ign.com"),
    )

    assert client.post.await_args.kwargs["json"]["include_domains"] == [
        "rockstargames.com",
        "ign.com",
    ]


@pytest.mark.asyncio
async def test_research_does_not_retry_deterministic_rejection() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = httpx.Response(
        401,
        text="invalid key",
        request=httpx.Request("POST", "https://api.tavily.com/search"),
    )
    sources = await ExternalResearchClient(_settings(), client=client).search(
        "query",
        max_results=5,
    )
    assert sources == []
    assert client.post.await_count == 1
