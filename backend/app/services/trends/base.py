"""
Classe base para coletadores de trends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class TrendColetada:
    """Trend coletada de uma fonte."""

    termo: str
    fonte: str
    payload: dict[str, Any]
    fonte_trend_nicho_id: str | None = None


class BaseTrendCollector(ABC):
    """Classe base para coletadores de trends."""

    def __init__(self, max_results: int = 15):
        self.max_results = max_results

    @abstractmethod
    async def collect(self, query: str, **kwargs) -> list[TrendColetada]:
        """
        Coleta trends de uma fonte específica.

        Args:
            query: Termo de busca ou identificador
            **kwargs: Parâmetros específicos da fonte

        Returns:
            Lista de trends coletadas
        """
