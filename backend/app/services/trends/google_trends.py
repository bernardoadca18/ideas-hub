"""
Coletador de trends do Google Trends via pytrends.
"""

import asyncio

import structlog
from pytrends.request import TrendReq  # type: ignore[import-untyped]

from app.core.config import settings
from app.services.trends.base import BaseTrendCollector
from app.services.trends.base import TrendColetada as TrendItem

logger = structlog.get_logger("services.trends.google")


class GoogleTrendsCollector(BaseTrendCollector):
    """Coleta trends do Google Trends via pytrends."""

    def __init__(self, max_results: int = 15):
        super().__init__(max_results)
        self.timeout = 10

    async def collect(self, query: str, **kwargs) -> list[TrendItem]:
        """
        Coleta trends relacionadas do Google Trends.

        Args:
            query: Termo de busca
            geo: Código de localização (opcional, padrão: Brasil)

        Returns:
            Lista de trends coletadas
        """
        geo = kwargs.get("geo", "BR")

        # Executa em thread separada pois pytrends é síncrono
        loop = asyncio.get_event_loop()
        trends = await loop.run_in_executor(
            None, self._fetch_related_queries, query, geo
        )

        return trends[: self.max_results]

    def _fetch_related_queries(self, query: str, geo: str) -> list[TrendItem]:
        """Busca queries relacionadas (síncrono)."""
        try:
            # Disable pytrends' legacy urllib3 Retry construction. Retrying here is
            # bounded and local, avoiding the old process-wide monkey-patch.
            pytrends = TrendReq(
                hl="pt-BR",
                tz=180,  # UTC-3 (Brasil)
                timeout=self.timeout,
                retries=0,
                backoff_factor=0,
            )

            # Constrói payload
            pytrends.build_payload(
                kw_list=[query],
                geo=geo,
                timeframe="now 7-d",  # Últimos 7 dias
            )

            # Busca queries relacionadas
            related = pytrends.related_queries()

            trends = []

            # Queries relacionadas - Top
            if query in related and related[query]["top"] is not None:
                for _, row in related[query]["top"].iterrows():
                    trends.append(
                        TrendItem(
                            termo=str(row["query"]),
                            fonte="google_trends",
                            payload={
                                "value": int(row["value"]) if "value" in row else None,
                                "type": "top",
                                "query_origem": query,
                                "geo": geo,
                            },
                        )
                    )

            # Queries relacionadas - Rising
            if query in related and related[query]["rising"] is not None:
                for _, row in related[query]["rising"].iterrows():
                    trends.append(
                        TrendItem(
                            termo=str(row["query"]),
                            fonte="google_trends",
                            payload={
                                "value": str(row["value"]) if "value" in row else None,
                                "type": "rising",
                                "query_origem": query,
                                "geo": geo,
                            },
                        )
                    )

            return trends

        except Exception as exc:  # noqa: BLE001 - pytrends exposes heterogeneous failures
            logger.warning(
                "trend_source_failure",
                source="google_trends",
                query=query,
                error_type=type(exc).__name__,
            )
            return []


# Instância global
google_trends_collector = GoogleTrendsCollector(
    max_results=settings.trends_max_por_fonte
)
