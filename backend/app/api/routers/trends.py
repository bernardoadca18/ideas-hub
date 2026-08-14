"""
Router CRUD para a entidade TrendColetada.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.trend_coletada_repository import TrendColetadaRepository
from app.schemas.trend_coletada import (
    TrendColetadaCreate,
    TrendColetadaUpdate,
    TrendColetadaResponse,
)
from app.services.trends.coletor import TrendsCollectorService


router = APIRouter(prefix="/trends", tags=["trends"])


def get_trend_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TrendColetadaRepository:
    return TrendColetadaRepository(db)


class ColetarRequest(BaseModel):
    """Request para coleta de trends."""
    nicho_id: UUID
    termos_adicionais: list[str] | None = None


class ColetarResponse(BaseModel):
    """Response da coleta de trends."""
    nicho_id: str
    total_coletado: int
    por_fonte: dict[str, int]
    erros: list[str] | None = None


@router.get("/", response_model=list[TrendColetadaResponse])
async def list_trends(
    repo: Annotated[TrendColetadaRepository, Depends(get_trend_repo)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    nicho_id: UUID | None = None,
    status: str | None = None,
    fonte: str | None = None,
):
    """Lista todas as trends coletadas com filtros opcionais."""
    return await repo.list(
        skip=skip,
        limit=limit,
        nicho_id=nicho_id,
        status=status,
        fonte=fonte,
    )


@router.post("/", response_model=TrendColetadaResponse, status_code=201)
async def create_trend(
    trend_data: TrendColetadaCreate,
    repo: Annotated[TrendColetadaRepository, Depends(get_trend_repo)],
):
    """Cria uma nova trend coletada."""
    return await repo.create(trend_data)


@router.post("/batch", response_model=list[TrendColetadaResponse], status_code=201)
async def create_trends_batch(
    trends_data: list[TrendColetadaCreate],
    repo: Annotated[TrendColetadaRepository, Depends(get_trend_repo)],
):
    """Cria múltiplas trends em lote."""
    return await repo.create_batch(trends_data)


@router.get("/{trend_id}", response_model=TrendColetadaResponse)
async def get_trend(
    trend_id: UUID,
    repo: Annotated[TrendColetadaRepository, Depends(get_trend_repo)],
):
    """Retorna uma trend coletada pelo ID."""
    trend = await repo.get_by_id(trend_id)
    if not trend:
        raise HTTPException(status_code=404, detail="Trend não encontrada")
    return trend


@router.put("/{trend_id}", response_model=TrendColetadaResponse)
async def update_trend(
    trend_id: UUID,
    trend_data: TrendColetadaUpdate,
    repo: Annotated[TrendColetadaRepository, Depends(get_trend_repo)],
):
    """Atualiza uma trend coletada existente."""
    trend = await repo.update(trend_id, trend_data)
    if not trend:
        raise HTTPException(status_code=404, detail="Trend não encontrada")
    return trend


@router.delete("/{trend_id}", status_code=204)
async def delete_trend(
    trend_id: UUID,
    repo: Annotated[TrendColetadaRepository, Depends(get_trend_repo)],
):
    """Remove uma trend coletada."""
    deleted = await repo.delete(trend_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trend não encontrada")


@router.post("/coletar", response_model=ColetarResponse, status_code=201)
async def coletar_trends(
    request: ColetarRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Coleta trends de todas as fontes configuradas para um nicho.

    Executa coleta em paralelo de:
    - Google Trends (para termos do nicho)
    - Reddit (subreddits configurados)
    - YouTube (canais/categorias configurados)
    - RSS (feeds configurados)

    Returns estatísticas da coleta.
    """
    collector = TrendsCollectorService(db)
    stats = await collector.collect_for_nicho(
        nicho_id=request.nicho_id,
        termos_adicionais=request.termos_adicionais
    )
    return stats


@router.patch("/{trend_id}/aprovar", response_model=TrendColetadaResponse)
async def aprovar_trend(
    trend_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Aprova uma trend coletada.

    Trends aprovadas podem ser usadas para geração de ideias.
    """
    collector = TrendsCollectorService(db)
    try:
        result = await collector.approve_trend(trend_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Recarrega para retornar objeto completo
    repo = TrendColetadaRepository(db)
    trend = await repo.get_by_id(trend_id)
    return trend


@router.patch("/{trend_id}/rejeitar", response_model=TrendColetadaResponse)
async def rejeitar_trend(
    trend_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Rejeita uma trend coletada.

    Trends rejeitadas não serão usadas para geração de ideias.
    """
    collector = TrendsCollectorService(db)
    try:
        result = await collector.reject_trend(trend_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Recarrega para retornar objeto completo
    repo = TrendColetadaRepository(db)
    trend = await repo.get_by_id(trend_id)
    return trend


class GerarIdeiasResponse(BaseModel):
    """Response da geração de ideias."""
    trend_id: str
    termo_trend: str
    ideias_geradas: int
    ideias: list[dict[str, str]]
    erros: list[str] | None = None


@router.post("/{trend_id}/gerar-ideias", response_model=GerarIdeiasResponse, status_code=201)
async def gerar_ideias_from_trend(
    trend_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    num_ideias: int | None = None,
):
    """
    Gera ideias a partir de uma trend aprovada.

    Para cada trend aprovada, gera N ideias (padrão: 3) que passam pelo
    Agente Curador para verificação de duplicidade/continuação.

    As ideias são criadas com status "rascunho" e ficam disponíveis
    para revisão e aprovação.

    Args:
        trend_id: ID da trend aprovada
        num_ideias: Número de ideias a gerar (opcional, padrão do config)

    Returns:
        Estatísticas da geração e lista de ideias criadas
    """
    from app.services.trends.gerador_ideias import get_trend_ideias_generator

    generator = get_trend_ideias_generator(db)

    try:
        resultado = await generator.generate_from_trend(
            trend_id=trend_id,
            num_ideias=num_ideias,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return resultado
