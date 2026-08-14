"""
Router CRUD para a entidade TrendColetada.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.trend_coletada_repository import TrendColetadaRepository
from app.schemas.trend_coletada import (
    TrendColetadaCreate,
    TrendColetadaUpdate,
    TrendColetadaResponse,
)


router = APIRouter(prefix="/trends", tags=["trends"])


def get_trend_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TrendColetadaRepository:
    return TrendColetadaRepository(db)


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
