"""
Coletador de trends de feeds RSS via feedparser.
"""

import asyncio

import feedparser  # type: ignore[import-untyped]
import structlog

from app.core.config import settings
from app.services.trends.base import BaseTrendCollector
from app.services.trends.base import TrendColetada as TrendItem

logger = structlog.get_logger("services.trends.rss")


class RSSCollector(BaseTrendCollector):
    """Coleta trends de feeds RSS."""

    def __init__(self, max_results: int = 15):
        super().__init__(max_results)

    async def collect(self, query: str, **kwargs) -> list[TrendItem]:
        """
        Coleta posts de um feed RSS.

        Args:
            query: URL do feed RSS

        Returns:
            Lista de trends coletadas
        """
        feed_url = query.strip()

        # Executa em thread separada pois feedparser é síncrono
        loop = asyncio.get_event_loop()
        trends = await loop.run_in_executor(None, self._parse_feed, feed_url)

        return trends[: self.max_results]

    def _parse_feed(self, feed_url: str) -> list[TrendItem]:
        """Parse do feed RSS (síncrono)."""
        try:
            feed = feedparser.parse(feed_url)

            if feed.bozo and not feed.entries:
                logger.warning(
                    "trend_source_failure",
                    source="rss",
                    error_type=type(feed.bozo_exception).__name__,
                )
                return []

            trends = []
            for entry in feed.entries[: self.max_results]:
                # Extrai título
                title = entry.get("title", entry.get("link", "Sem título"))

                # Extrai data de publicação
                published = entry.get("published", entry.get("updated", ""))

                # Extrai resumo/descrição
                summary = entry.get("summary", entry.get("description", ""))

                trends.append(
                    TrendItem(
                        termo=title[:300],
                        fonte="rss",
                        payload={
                            "link": entry.get("link"),
                            "published": published,
                            "summary": summary[:500] if summary else None,
                            "author": entry.get("author"),
                            "tags": [tag.term for tag in entry.get("tags", [])]
                            if "tags" in entry
                            else [],
                            "feed_url": feed_url,
                            "feed_title": feed.feed.get("title"),
                        },
                    )
                )

            return trends

        except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
            logger.warning(
                "trend_source_failure",
                source="rss",
                error_type=type(exc).__name__,
            )
            return []


# Instância global
rss_collector = RSSCollector(max_results=settings.trends_max_por_fonte)
