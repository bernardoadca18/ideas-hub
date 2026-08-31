from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.agents.curador import IdeiaBruta, IdeiaRefinada
from app.repositories.ideia_repository import SimilarIdeaMatch
from app.services.trends.gerador_ideias import TrendIdeiasGenerator


@pytest.mark.asyncio
async def test_trend_generation_sends_real_similarity_to_curator():
    repository = AsyncMock()
    similar_idea = SimpleNamespace(id=uuid4(), titulo="Ideia realmente próxima")
    repository.find_similar.return_value = [
        SimilarIdeaMatch(idea=similar_idea, similarity=0.9725)
    ]
    repository.create.return_value = SimpleNamespace(id=uuid4())
    repository.get_by_id.return_value = repository.create.return_value
    service = TrendIdeiasGenerator.__new__(TrendIdeiasGenerator)
    service.ideia_repo = repository
    trend = SimpleNamespace(
        id=uuid4(), nicho_id=uuid4(), payload_raw=None, fonte="rss", termo_bruto="tema"
    )

    with (
        patch.object(
            service,
            "_generate_ideia_bruta",
            AsyncMock(return_value=IdeiaBruta(titulo="Nova", descricao=None)),
        ),
        patch(
            "app.services.trends.gerador_ideias.embedding_service.generate_for_ideia",
            AsyncMock(return_value=[0.1, 0.2]),
        ),
        patch(
            "app.services.trends.gerador_ideias.curador_service.processar",
            AsyncMock(
                return_value=IdeiaRefinada(
                    titulo="Nova refinada",
                    descricao_breve="Descrição",
                    justificativa_llm="Motivo",
                    eh_duplicada=True,
                )
            ),
        ) as curator,
    ):
        await service._generate_single_ideia(trend, None, None, 1, 1)

    assert curator.await_args.kwargs["ideias_similares"] == [
        {
            "id": str(similar_idea.id),
            "titulo": "Ideia realmente próxima",
            "similaridade": 0.9725,
        }
    ]
