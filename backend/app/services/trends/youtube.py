"""
Coletador de trends do YouTube via Data API v3.
"""

import httpx
import structlog

from app.core.config import settings
from app.services.trends.base import BaseTrendCollector
from app.services.trends.base import TrendColetada as TrendItem

logger = structlog.get_logger("services.trends.youtube")


class YouTubeCollector(BaseTrendCollector):
    """Coleta trends do YouTube via Data API v3."""

    def __init__(self, max_results: int = 15):
        super().__init__(max_results)
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.api_key = settings.youtube_api_key

    async def collect(self, query: str, **kwargs) -> list[TrendItem]:
        """
        Coleta vídeos populares ou busca por termo.

        Args:
            query: Termo de busca ou categoria ID
            mode: 'search' para busca, 'videos' para populares (padrão: search)
            region_code: Código da região (padrão: BR)

        Returns:
            Lista de trends coletadas
        """
        if not self.api_key:
            logger.info("trend_source_unconfigured", source="youtube")
            return []

        mode = kwargs.get("mode", "search")
        region_code = kwargs.get("region_code", "BR")

        if mode == "videos":
            return await self._fetch_popular_videos(region_code, query)
        else:
            return await self._search_videos(query, region_code)

    async def _search_videos(self, query: str, region_code: str) -> list[TrendItem]:
        """Busca vídeos por termo."""
        url = f"{self.base_url}/search"
        params: dict[str, str | int] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "relevance",
            "maxResults": self.max_results,
            "regionCode": region_code,
            "key": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            trends = []
            for item in data.get("items", []):
                snippet = item["snippet"]
                video_id = item["id"]["videoId"]

                trends.append(
                    TrendItem(
                        termo=snippet["title"][:300],
                        fonte="youtube",
                        payload={
                            "video_id": video_id,
                            "channel_title": snippet["channelTitle"],
                            "description": snippet.get("description", "")[:500],
                            "published_at": snippet["publishedAt"],
                            "thumbnail": snippet["thumbnails"]
                            .get("default", {})
                            .get("url"),
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "mode": "search",
                            "query": query,
                        },
                    )
                )

            return trends

        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "trend_source_failure",
                source="youtube",
                operation="search",
                error_type=type(exc).__name__,
            )
            return []

    async def _fetch_popular_videos(
        self, region_code: str, category_id: str | None = None
    ) -> list[TrendItem]:
        """Busca vídeos mais populares."""
        url = f"{self.base_url}/videos"
        params: dict[str, str | int] = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "maxResults": self.max_results,
            "regionCode": region_code,
            "key": self.api_key,
        }

        if category_id:
            params["videoCategoryId"] = category_id

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            trends = []
            for item in data.get("items", []):
                snippet = item["snippet"]
                stats = item.get("statistics", {})
                video_id = item["id"]

                trends.append(
                    TrendItem(
                        termo=snippet["title"][:300],
                        fonte="youtube",
                        payload={
                            "video_id": video_id,
                            "channel_title": snippet["channelTitle"],
                            "view_count": stats.get("viewCount", 0),
                            "like_count": stats.get("likeCount", 0),
                            "comment_count": stats.get("commentCount", 0),
                            "category_id": snippet.get("categoryId"),
                            "published_at": snippet["publishedAt"],
                            "thumbnail": snippet["thumbnails"]
                            .get("default", {})
                            .get("url"),
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "mode": "popular",
                        },
                    )
                )

            return trends

        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "trend_source_failure",
                source="youtube",
                operation="popular",
                error_type=type(exc).__name__,
            )
            return []


# Instância global
youtube_collector = YouTubeCollector(max_results=settings.trends_max_por_fonte)
