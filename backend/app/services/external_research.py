"""Bounded, pooled external research boundary for untrusted evidence."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.core.config import Settings, settings
from app.services.llm_gateway import is_retryable_status

logger = structlog.get_logger("services.external_research")


@dataclass(frozen=True)
class ResearchSource:
    source_id: str
    query: str
    title: str
    url: str
    snippet: str
    source_type: str
    retrieved_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExternalResearchClient:
    """Tavily adapter with one pool per process and optional-service semantics."""

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
                    connect=self.config.tavily_connect_timeout_seconds,
                    read=self.config.tavily_read_timeout_seconds,
                    write=10.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            )
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ResearchSource]:
        if not self.config.tavily_api_key or not query.strip():
            return []
        last_error: Exception | None = None
        for attempt in range(1, self.config.tavily_max_attempts + 1):
            try:
                response = await self._get_client().post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {self.config.tavily_api_key}"},
                    json={
                        "query": query,
                        "max_results": max_results,
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                )
                if response.status_code >= 400:
                    if not is_retryable_status(response.status_code):
                        logger.warning(
                            "external_research_rejected",
                            status_code=response.status_code,
                            query_identity=_identity(query),
                        )
                        return []
                    response.raise_for_status()
                payload = response.json()
                results = payload.get("results")
                if not isinstance(results, list):
                    raise TypeError("Tavily response.results is not a list")
                retrieved_at = datetime.now(UTC).isoformat()
                sources: list[ResearchSource] = []
                for index, item in enumerate(results[:max_results], start=1):
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "").strip()
                    snippet = str(item.get("content") or "").strip()[:1200]
                    if not url or not snippet:
                        continue
                    sources.append(
                        ResearchSource(
                            source_id=f"external-{_identity(query + url)[:16]}-{index}",
                            query=query,
                            title=str(item.get("title") or "Sem título")[:300],
                            url=url,
                            snippet=snippet,
                            source_type="external_search_result",
                            retrieved_at=retrieved_at,
                        )
                    )
                logger.info(
                    "external_research_completed",
                    query_identity=_identity(query),
                    result_count=len(sources),
                    attempt=attempt,
                )
                return sources
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.HTTPStatusError,
            ) as exc:
                last_error = exc
                if attempt < self.config.tavily_max_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "external_research_malformed_response",
                    error_type=type(exc).__name__,
                )
                return []
        logger.warning(
            "external_research_unavailable",
            error_type=type(last_error).__name__ if last_error else "unknown",
        )
        return []

    async def search_text(self, query: str, *, max_results: int) -> str:
        sources = await self.search(query, max_results=max_results)
        return "\n".join(
            f"- {item.title}: {item.snippet} ({item.url})" for item in sources
        )


def _identity(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


external_research_client = ExternalResearchClient()
