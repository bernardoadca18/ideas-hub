"""
Serviço coordenador de coleta de trends.

Executa múltiplas fontes em paralelo via asyncio.gather.
"""
import asyncio
from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.fonte_trend_nicho import FonteTrendNicho
from app.repositories.trend_coletada_repository import TrendColetadaRepository
from app.repositories.fonte_trend_nicho_repository import FonteTrendNichoRepository
from app.schemas.trend_coletada import TrendColetadaCreate
from app.services.trends.google_trends import google_trends_collector
from app.services.trends.reddit_publico import reddit_publico_collector
from app.services.trends.youtube import youtube_collector
from app.services.trends.rss import rss_collector
from app.services.trends.base import TrendColetada as TrendItem


class TrendsCollectorService:
    """Coordena coleta de trends de múltiplas fontes."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.trend_repo = TrendColetadaRepository(session)
        self.fonte_repo = FonteTrendNichoRepository(session)

        # Mapeia tipos para coletores
        self.collectors = {
            'google_trends': google_trends_collector,
            'reddit_publico': reddit_publico_collector,
            'youtube': youtube_collector,
            'youtube_categoria': youtube_collector,
            'youtube_busca': youtube_collector,
            'rss': rss_collector,
        }

    async def collect_for_nicho(
        self,
        nicho_id: UUID,
        termos_adicionais: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Coleta trends de todas as fontes configuradas para um nicho.

        Args:
            nicho_id: ID do nicho
            termos_adicionais: Termos extras para busca (ex: termos do prompt)

        Returns:
            Dict com estatísticas da coleta
        """
        # 1. Busca fontes configuradas para o nicho
        fontes = await self.fonte_repo.list_by_nicho(nicho_id, ativo=True)

        # 2. Prepara tarefas de coleta
        tasks = []

        # Adiciona Google Trends para termos do nicho
        if termos_adicionais:
            for termo in termos_adicionais[:3]:  # Limite de 3 termos
                tasks.append(self._collect_google_trends(nicho_id, termo))

        # Adiciona fontes configuradas (Reddit, YouTube, RSS)
        for fonte in fontes:
            task = self._collect_from_fonte(nicho_id, fonte)
            tasks.append(task)

        # 3. Executa todas em paralelo
        if not tasks:
            return {
                'nicho_id': str(nicho_id),
                'total_coletado': 0,
                'por_fonte': {},
                'erro': 'Nenhuma fonte configurada'
            }

        resultados = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. Processa resultados
        stats = {
            'nicho_id': str(nicho_id),
            'total_coletado': 0,
            'por_fonte': {},
            'erros': []
        }

        for resultado in resultados:
            if isinstance(resultado, Exception):
                stats['erros'].append(str(resultado))
            elif isinstance(resultado, dict):
                fonte = resultado.get('fonte', 'desconhecida')
                # Normaliza fonte para estatísticas
                if fonte.startswith('youtube_'):
                    fonte = 'youtube'
                count = resultado.get('count', 0)
                stats['por_fonte'][fonte] = count
                stats['total_coletado'] += count

        return stats

    async def _collect_google_trends(self, nicho_id: UUID, termo: str) -> dict:
        """Coleta trends do Google Trends para um termo."""
        try:
            trends = await google_trends_collector.collect(termo)
            return await self._save_trends(nicho_id, trends, 'google_trends')
        except Exception as e:
            print(f"Erro Google Trends '{termo}': {e}")
            return {'fonte': 'google_trends', 'count': 0, 'error': str(e)}

    async def _collect_from_fonte(
        self,
        nicho_id: UUID,
        fonte: FonteTrendNicho
    ) -> dict:
        """Coleta trends de uma fonte configurada."""
        try:
            collector = self.collectors.get(fonte.tipo)
            if not collector:
                return {'fonte': fonte.tipo, 'count': 0, 'error': 'Coletor não encontrado'}

            # Parâmetros específicos por tipo
            kwargs = {}
            if fonte.tipo == 'reddit_publico':
                kwargs['sorting'] = 'hot'
            elif fonte.tipo == 'youtube_categoria':
                # Para YouTube, identificador é o category ID
                kwargs['mode'] = 'videos'

            trends = await collector.collect(fonte.identificador, **kwargs)

            # Salva com referência à fonte
            return await self._save_trends(
                nicho_id,
                trends,
                fonte.tipo,
                fonte_trend_nicho_id=str(fonte.id)
            )

        except Exception as e:
            print(f"Erro {fonte.tipo} '{fonte.identificador}': {e}")
            return {'fonte': fonte.tipo, 'count': 0, 'error': str(e)}

    async def _save_trends(
        self,
        nicho_id: UUID,
        trends: list[TrendItem],
        fonte: str,
        fonte_trend_nicho_id: str | None = None
    ) -> dict:
        """Salva trends no banco."""
        if not trends:
            return {'fonte': fonte, 'count': 0}

        # Normaliza fonte para o enum do banco (youtube_categoria -> youtube, etc)
        fonte_normalizada = fonte
        if fonte.startswith('youtube_'):
            fonte_normalizada = 'youtube'

        # Converte para schema de criação
        trends_data = []
        for trend in trends:
            trends_data.append(TrendColetadaCreate(
                nicho_id=nicho_id,
                fonte_trend_nicho_id=UUID(fonte_trend_nicho_id) if fonte_trend_nicho_id else None,
                termo_bruto=trend.termo,
                fonte=fonte_normalizada,
                status='pendente',
                payload_raw=trend.payload
            ))

        # Salva em lote
        created = await self.trend_repo.create_batch(trends_data)

        return {
            'fonte': fonte,
            'count': len(created),
            'amostra': [t.termo_bruto for t in created[:3]]
        }

    async def approve_trend(self, trend_id: UUID) -> dict:
        """Aprova uma trend."""
        from app.schemas.trend_coletada import TrendColetadaUpdate

        trend = await self.trend_repo.update(
            trend_id,
            TrendColetadaUpdate(status='aprovada')
        )

        if not trend:
            raise ValueError("Trend não encontrada")

        return {
            'id': str(trend.id),
            'status': trend.status,
            'termo': trend.termo_bruto
        }

    async def reject_trend(self, trend_id: UUID) -> dict:
        """Rejeita uma trend."""
        from app.schemas.trend_coletada import TrendColetadaUpdate

        trend = await self.trend_repo.update(
            trend_id,
            TrendColetadaUpdate(status='rejeitada')
        )

        if not trend:
            raise ValueError("Trend não encontrada")

        return {
            'id': str(trend.id),
            'status': trend.status,
            'termo': trend.termo_bruto
        }
