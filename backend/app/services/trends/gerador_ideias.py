"""
Serviço para gerar ideias a partir de trends aprovadas.

Para cada trend aprovada, gera N ideias que passam pelo Agente Curador.
"""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.curador import IdeiaBruta, curador_service
from app.core.config import settings
from app.core.logging import gerador_ideias_logger
from app.models.trend_coletada import TrendColetada
from app.repositories.fonte_trend_nicho_repository import FonteTrendNichoRepository
from app.repositories.ideia_repository import IdeiaRepository
from app.repositories.nicho_repository import NichoRepository
from app.repositories.trend_coletada_repository import TrendColetadaRepository
from app.schemas.ideia import IdeiaCreate
from app.services.embeddings import embedding_service


class TrendIdeiasGenerator:
    """Gera ideias a partir de trends aprovadas."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.trend_repo = TrendColetadaRepository(session)
        self.ideia_repo = IdeiaRepository(session)
        self.nicho_repo = NichoRepository(session)
        self.fonte_repo = FonteTrendNichoRepository(session)

    async def generate_from_trend(
        self,
        trend_id: UUID,
        num_ideias: int | None = None,
    ) -> dict[str, Any]:
        num_ideias = num_ideias or settings.ideias_por_trend

        metrics = gerador_ideias_logger.start_operation(operation="generate_from_trend", trend_id=str(trend_id))

        try:
            trend = await self.trend_repo.get_by_id(trend_id)
            if not trend:
                raise ValueError("Trend não encontrada")

            if trend.status != "aprovada":
                raise ValueError(f"Trend não está aprovada (status: {trend.status})")

            prompt_nicho = None
            perfil_id = None
            nicho_id = None
            if trend.nicho_id:
                nicho = await self.nicho_repo.get_by_id(trend.nicho_id)
                if nicho:
                    prompt_nicho = nicho.prompt_ideacao
                    perfil_id = nicho.perfil_producao
                    nicho_id = str(trend.nicho_id)

            ideias_geradas = []
            erros = []

            for i in range(num_ideias):
                try:
                    ideia = await self._generate_single_ideia(
                        trend=trend,
                        prompt_nicho=prompt_nicho,
                        perfil_id=perfil_id,
                        indice=i + 1,
                        total=num_ideias,
                    )
                    ideias_geradas.append(ideia)
                except Exception as e:  # noqa: BLE001 - isolate one failed trend candidate
                    erros.append(f"Ideia {i+1}: {e!s}")
                    print(f"Erro ao gerar ideia {i+1}: {e}")

            resultado = {
                'trend_id': str(trend_id),
                'termo_trend': trend.termo_bruto,
                'ideias_geradas': len(ideias_geradas),
                'ideias': [
                    {'id': str(ideia.id), 'titulo': ideia.titulo, 'status': ideia.status}
                    for ideia in ideias_geradas
                ],
                'erros': erros if erros else None,
            }

            gerador_ideias_logger.end_operation(
                metrics=metrics, success=True, num_ideias_geradas=len(ideias_geradas), nicho_id=nicho_id,
            )

            return resultado

        except Exception as e:
            gerador_ideias_logger.end_operation(metrics=metrics, success=False, error=str(e))
            raise

    async def _generate_single_ideia(
        self,
        trend: TrendColetada,
        prompt_nicho: str | None,
        perfil_id: str | None,
        indice: int,
        total: int,
    ):
        ideia_bruta = await self._generate_ideia_bruta(
            trend=trend, prompt_nicho=prompt_nicho, perfil_id=perfil_id, indice=indice, total=total,
        )

        embedding = await embedding_service.generate_for_ideia(ideia_bruta.titulo, ideia_bruta.descricao)

        similares = await self.ideia_repo.find_similar(
            embedding=embedding, threshold=settings.ideia_similarity_threshold, exclude_id=None, limit=3,
        )

        ideias_similares = (
            [
                {
                    "id": str(match.idea.id),
                    "titulo": match.idea.titulo,
                    "similaridade": match.similarity,
                }
                for match in similares
            ]
            if similares
            else None
        )

        ideia_refinada = await curador_service.processar(
            ideia_bruta=ideia_bruta,
            prompt_nicho=prompt_nicho,
            ideias_similares=ideias_similares,
            perfil_id=perfil_id,
        )

        nova_ideia_data = IdeiaCreate(
            nicho_id=trend.nicho_id,
            origem="trend",
            titulo=ideia_refinada.titulo,
            descricao_breve=ideia_refinada.descricao_breve,
            status="rascunho",
            eh_continuacao_de=None,
            numero_parte=None,
            fonte_trend_id=trend.id,
            justificativa_llm=ideia_refinada.justificativa_llm,
        )

        ideia_criada = await self.ideia_repo.create(nova_ideia_data)
        await self.ideia_repo.update_embedding(ideia_criada.id, embedding)
        ideia_recarregada = await self.ideia_repo.get_by_id(ideia_criada.id)
        assert ideia_recarregada is not None
        return ideia_recarregada

    async def _generate_ideia_bruta(
        self,
        trend: TrendColetada,
        prompt_nicho: str | None,
        perfil_id: str | None,
        indice: int,
        total: int,
    ) -> IdeiaBruta:
        contexto_fonte = None
        if trend.payload_raw:
            if trend.fonte == "youtube" and trend.payload_raw.get("title"):
                contexto_fonte = f"Vídeo original: {trend.payload_raw['title']}"
            elif trend.fonte == "reddit_publico" and trend.payload_raw.get("subreddit"):
                contexto_fonte = f"Subreddit: r/{trend.payload_raw['subreddit']}"
            elif trend.fonte == "rss" and trend.payload_raw.get("source"):
                contexto_fonte = f"Fonte RSS: {trend.payload_raw['source']}"

        return await curador_service.gerar_ideia_bruta(
            termo_trend=trend.termo_bruto,
            contexto_fonte=contexto_fonte,
            prompt_nicho=prompt_nicho,
            indice=indice,
            total=total,
            perfil_id=perfil_id,
        )


trend_ideias_generator = None


def get_trend_ideias_generator(session: AsyncSession) -> TrendIdeiasGenerator:
    return TrendIdeiasGenerator(session)
