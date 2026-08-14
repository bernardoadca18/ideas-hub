"""
Serviço para gerar ideias a partir de trends aprovadas.

Para cada trend aprovada, gera N ideias que passam pelo Agente Curador.
"""
from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.trend_coletada import TrendColetada
from app.repositories.trend_coletada_repository import TrendColetadaRepository
from app.repositories.ideia_repository import IdeiaRepository
from app.repositories.nicho_repository import NichoRepository
from app.repositories.fonte_trend_nicho_repository import FonteTrendNichoRepository
from app.schemas.ideia import IdeiaCreate
from app.agents.curador import curador_service, IdeiaBruta
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
        """
        Gera ideias a partir de uma trend aprovada.

        Args:
            trend_id: ID da trend aprovada
            num_ideias: Número de ideias a gerar (padrão: settings.ideias_por_trend)

        Returns:
            Dict com estatísticas da geração
        """
        num_ideias = num_ideias or settings.ideias_por_trend

        # 1. Verifica se a trend existe e está aprovada
        trend = await self.trend_repo.get_by_id(trend_id)
        if not trend:
            raise ValueError("Trend não encontrada")

        if trend.status != "aprovada":
            raise ValueError(f"Trend não está aprovada (status: {trend.status})")

        # 2. Busca o nicho para obter prompt de ideação
        prompt_nicho = None
        if trend.nicho_id:
            nicho = await self.nicho_repo.get_by_id(trend.nicho_id)
            if nicho:
                prompt_nicho = nicho.prompt_ideacao

        # 3. Gera N ideias a partir da trend
        ideias_geradas = []
        erros = []

        for i in range(num_ideias):
            try:
                ideia = await self._generate_single_ideia(
                    trend=trend,
                    prompt_nicho=prompt_nicho,
                    indice=i + 1,
                    total=num_ideias,
                )
                ideias_geradas.append(ideia)
            except Exception as e:
                erros.append(f"Ideia {i+1}: {str(e)}")
                print(f"Erro ao gerar ideia {i+1}: {e}")

        return {
            'trend_id': str(trend_id),
            'termo_trend': trend.termo_bruto,
            'ideias_geradas': len(ideias_geradas),
            'ideias': [
                {
                    'id': str(ideia.id),
                    'titulo': ideia.titulo,
                    'status': ideia.status,
                }
                for ideia in ideias_geradas
            ],
            'erros': erros if erros else None,
        }

    async def _generate_single_ideia(
        self,
        trend: TrendColetada,
        prompt_nicho: str | None,
        indice: int,
        total: int,
    ):
        """
        Gera uma única ideia a partir da trend.

        Args:
            trend: Trend aprovada
            prompt_nicho: Prompt de ideação do nicho
            indice: Índice da ideia (1 a N)
            total: Total de ideias a gerar

        Returns:
            Ideia criada
        """
        # 1. Gera ideia bruta via LLM
        ideia_bruta = await self._generate_ideia_bruta(
            trend=trend,
            prompt_nicho=prompt_nicho,
            indice=indice,
            total=total,
        )

        # 2. Gera embedding para busca de similaridade
        embedding = await embedding_service.generate_for_ideia(
            ideia_bruta.titulo,
            ideia_bruta.descricao
        )

        # 3. Busca ideias similares
        similares = await self.ideia_repo.find_similar(
            embedding=embedding,
            threshold=settings.ideia_similarity_threshold,
            exclude_id=None,
            limit=3
        )

        # Converte para formato esperado pelo curador
        ideias_similares = [
            {
                "id": str(s.id),
                "titulo": s.titulo,
                "similaridade": 1 - 0.15,  # Aproximação
            }
            for s in similares
        ] if similares else None

        # 4. Processa via Agente Curador
        ideia_refinada = await curador_service.processar(
            ideia_bruta=ideia_bruta,
            prompt_nicho=prompt_nicho,
            ideias_similares=ideias_similares,
        )

        # 5. Cria a ideia no banco
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

        # 6. Atualiza o embedding
        await self.ideia_repo.update_embedding(ideia_criada.id, embedding)

        # 7. Recarrega para garantir que todos os atributos estão disponíveis
        ideia_criada = await self.ideia_repo.get_by_id(ideia_criada.id)

        return ideia_criada

    async def _generate_ideia_bruta(
        self,
        trend: TrendColetada,
        prompt_nicho: str | None,
        indice: int,
        total: int,
    ) -> IdeiaBruta:
        """
        Gera uma ideia bruta a partir da trend usando LLM.

        Args:
            trend: Trend aprovada
            prompt_nicho: Prompt de ideação do nicho
            indice: Índice da ideia (1 a N)
            total: Total de ideias a gerar

        Returns:
            IdeiaBruta gerada
        """
        # Monta prompt para geração de ideia
        sistema_prompt = """Você é um gerador de ideias para vídeos. Sua função é criar ideias originais e atraentes a partir de trends e tópicos populares.

Regras:
- Crie ideias que sejam práticas e viáveis para vídeos
- Seja criativo mas mantendo relevância para o tema
- Cada ideia deve ser única e diferente das outras
- Considere o contexto da trend e o nicho do canal
- Varie o ângulo de abordagem (tutorial, análise, opinião, curiosidade, etc.)

Responda APENAS no formato JSON:
{
  "titulo": "Título da ideia (máximo 80 caracteres)",
  "descricao": "Descrição breve da ideia (máximo 200 caracteres)"
}"""

        # Monta contexto
        usuario_parts = [
            f"Trend/Topic: {trend.termo_bruto}",
            f"Fonte: {trend.fonte}",
        ]

        if trend.payload_raw:
            # Adiciona contexto adicional do payload
            if trend.fonte == "youtube" and trend.payload_raw.get("title"):
                usuario_parts.append(f"Vídeo original: {trend.payload_raw['title']}")
            elif trend.fonte == "reddit_publico" and trend.payload_raw.get("subreddit"):
                usuario_parts.append(f"Subreddit: r/{trend.payload_raw['subreddit']}")
            elif trend.fonte == "rss" and trend.payload_raw.get("source"):
                usuario_parts.append(f"Fonte RSS: {trend.payload_raw['source']}")

        if prompt_nicho:
            usuario_parts.append(f"\nNicho do canal: {prompt_nicho}")

        usuario_parts.append(f"\nGere a ideia {indice} de {total}. Seja criativo e varie a abordagem.")

        usuario_message = "\n".join(usuario_parts)

        # Chama LLM
        try:
            resposta_llm = await curador_service._call_llm(
                messages=[
                    {"role": "system", "content": sistema_prompt},
                    {"role": "user", "content": usuario_message},
                ],
                temperature=0.8,  # Temperatura mais alta para criatividade
            )

            # Parse da resposta JSON
            import json
            if "```json" in resposta_llm:
                resposta_llm = resposta_llm.split("```json")[1].split("```")[0]
            elif "```" in resposta_llm:
                resposta_llm = resposta_llm.split("```")[1].split("```")[0]

            dados = json.loads(resposta_llm.strip())
            titulo = dados.get("titulo", trend.termo_bruto)
            descricao = dados.get("descricao", "")

        except Exception as e:
            print(f"Erro ao gerar ideia via LLM: {e}")
            # Fallback: usa termo da trend como título
            titulo = f"{trend.termo_bruto[:70]} - Ideia {indice}"
            descricao = f"Ideia gerada a partir da trend: {trend.termo_bruto}"

        return IdeiaBruta(
            titulo=titulo[:300],
            descricao=descricao[:500] if descricao else None,
            nicho_id=str(trend.nicho_id) if trend.nicho_id else None,
            origem="trend",
        )


# Instância global
trend_ideias_generator = None


def get_trend_ideias_generator(session: AsyncSession) -> TrendIdeiasGenerator:
    """Factory para criar instância do gerador."""
    return TrendIdeiasGenerator(session)
