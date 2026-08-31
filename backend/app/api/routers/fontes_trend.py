"""
Router CRUD para a entidade FonteTrendNicho.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.fonte_trend_nicho_repository import FonteTrendNichoRepository
from app.schemas.fonte_trend_nicho import (
    FonteTrendNichoCreate,
    FonteTrendNichoResponse,
    FonteTrendNichoUpdate,
)

router = APIRouter(prefix="/fontes-trend", tags=["fontes-trend"])


def get_fonte_repo(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FonteTrendNichoRepository:
    return FonteTrendNichoRepository(db)


@router.get("/", response_model=list[FonteTrendNichoResponse])
async def list_fontes(
    repo: Annotated[FonteTrendNichoRepository, Depends(get_fonte_repo)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    nicho_id: UUID | None = None,
    tipo: str | None = None,
    ativo: bool | None = None,
):
    """Lista todas as fontes de trend configuradas."""
    return await repo.list(
        skip=skip,
        limit=limit,
        nicho_id=nicho_id,
        tipo=tipo,
        ativo=ativo,
    )


@router.post("/", response_model=FonteTrendNichoResponse, status_code=201)
async def create_fonte(
    fonte_data: FonteTrendNichoCreate,
    repo: Annotated[FonteTrendNichoRepository, Depends(get_fonte_repo)],
):
    """Cria uma nova fonte de trend para um nicho."""
    return await repo.create(fonte_data)


@router.get("/{fonte_id}", response_model=FonteTrendNichoResponse)
async def get_fonte(
    fonte_id: UUID,
    repo: Annotated[FonteTrendNichoRepository, Depends(get_fonte_repo)],
):
    """Retorna uma fonte de trend pelo ID."""
    fonte = await repo.get_by_id(fonte_id)
    if not fonte:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    return fonte


@router.put("/{fonte_id}", response_model=FonteTrendNichoResponse)
async def update_fonte(
    fonte_id: UUID,
    fonte_data: FonteTrendNichoUpdate,
    repo: Annotated[FonteTrendNichoRepository, Depends(get_fonte_repo)],
):
    """Atualiza uma fonte de trend existente."""
    fonte = await repo.update(fonte_id, fonte_data)
    if not fonte:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    return fonte


@router.delete("/{fonte_id}", status_code=204)
async def delete_fonte(
    fonte_id: UUID,
    repo: Annotated[FonteTrendNichoRepository, Depends(get_fonte_repo)],
):
    """Remove uma fonte de trend."""
    deleted = await repo.delete(fonte_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
