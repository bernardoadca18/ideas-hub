"""
Coletador de trends do Reddit via JSON público (sem API key).
"""

import httpx
import structlog

from app.core.config import settings
from app.services.trends.base import BaseTrendCollector
from app.services.trends.base import TrendColetada as TrendItem

logger = structlog.get_logger("services.trends.reddit")


class RedditPublicoCollector(BaseTrendCollector):
    """Coleta trends do Reddit via JSON público."""

    def __init__(self, max_results: int = 15):
        super().__init__(max_results)
        self.base_url = "https://www.reddit.com"
        self.user_agent = settings.reddit_public_user_agent

    async def collect(self, query: str, **kwargs) -> list[TrendItem]:
        """
        Coleta posts populares de um subreddit.

        Args:
            query: Nome do subreddit (sem r/)
            sorting: Ordenação (hot, new, top, rising) - padrão: hot
            timeframe: Período para top (hour, day, week, month, year, all) - padrão: day

        Returns:
            Lista de trends coletadas
        """
        subreddit = query.strip().replace("r/", "")
        sorting = kwargs.get("sorting", "hot")
        timeframe = kwargs.get("timeframe", "day")

        trends = await self._fetch_posts(subreddit, sorting, timeframe)
        return trends[: self.max_results]

    async def _fetch_posts(
        self, subreddit: str, sorting: str = "hot", timeframe: str = "day"
    ) -> list[TrendItem]:
        """Busca posts de um subreddit."""
        url = f"{self.base_url}/r/{subreddit}/{sorting}.json?t={timeframe}&limit={self.max_results}"

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

            trends = []
            for child in data["data"]["children"]:
                post = child["data"]

                # Usa título do post como termo
                trends.append(
                    TrendItem(
                        termo=post["title"][:300],  # Limite do campo
                        fonte="reddit_publico",
                        payload={
                            "subreddit": post["subreddit"],
                            "score": post["score"],
                            "num_comments": post["num_comments"],
                            "author": post.get("author", "[deleted]"),
                            "permalink": post["permalink"],
                            "url": f"https://reddit.com{post['permalink']}",
                            "created_utc": post["created_utc"],
                            "sorting": sorting,
                            "timeframe": timeframe,
                        },
                    )
                )

            return trends

        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "trend_source_failure",
                source="reddit_publico",
                subreddit=subreddit,
                error_type=type(exc).__name__,
            )
            return []


# Instância global
reddit_publico_collector = RedditPublicoCollector(
    max_results=settings.trends_max_por_fonte
)
