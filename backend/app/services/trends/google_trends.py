"""
Coletador de trends do Google Trends via pytrends.
"""
import asyncio
from typing import Any

# Monkey-patch para compatibilidade urllib3 >= 2.0 com pytrends
# pytrends ainda usa method_whitelist que foi removido no urllib3 2.0
from urllib3.util import retry
original_init = retry.Retry.__init__

def patched_init(self, *args, method_whitelist=None, **kwargs):
    # Converte method_whitelist (deprecated) para allowed_methods
    if method_whitelist is not None and 'allowed_methods' not in kwargs:
        kwargs['allowed_methods'] = method_whitelist
    return original_init(self, *args, **kwargs)

retry.Retry.__init__ = patched_init

from pytrends.request import TrendReq

from app.services.trends.base import BaseTrendCollector, TrendColetada as TrendItem
from app.core.config import settings


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
            None,
            self._fetch_related_queries,
            query,
            geo
        )

        return trends[:self.max_results]

    def _fetch_related_queries(self, query: str, geo: str) -> list[TrendItem]:
        """Busca queries relacionadas (síncrono)."""
        try:
            pytrends = TrendReq(
                hl='pt-BR',
                tz=180,  # UTC-3 (Brasil)
                timeout=self.timeout,
                retries=2,
                backoff_factor=0.5
            )

            # Constrói payload
            pytrends.build_payload(
                kw_list=[query],
                geo=geo,
                timeframe='now 7-d'  # Últimos 7 dias
            )

            # Busca queries relacionadas
            related = pytrends.related_queries()

            trends = []

            # Queries relacionadas - Top
            if query in related and related[query]['top'] is not None:
                for _, row in related[query]['top'].iterrows():
                    trends.append(TrendItem(
                        termo=str(row['query']),
                        fonte='google_trends',
                        payload={
                            'value': int(row['value']) if 'value' in row else None,
                            'type': 'top',
                            'query_origem': query,
                            'geo': geo
                        }
                    ))

            # Queries relacionadas - Rising
            if query in related and related[query]['rising'] is not None:
                for _, row in related[query]['rising'].iterrows():
                    trends.append(TrendItem(
                        termo=str(row['query']),
                        fonte='google_trends',
                        payload={
                            'value': str(row['value']) if 'value' in row else None,
                            'type': 'rising',
                            'query_origem': query,
                            'geo': geo
                        }
                    ))

            return trends

        except Exception as e:
            print(f"Erro ao buscar Google Trends para '{query}': {e}")
            return []


# Instância global
google_trends_collector = GoogleTrendsCollector(max_results=settings.trends_max_por_fonte)
