"""
Router CRUD para a entidade Ideia.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.ideia_repository import IdeiaRepository
from app.schemas.ideia import IdeiaCreate, IdeiaUpdate, IdeiaResponse


router = APIRouter(prefix="/ideias", tags=["ideias"])


def get_ideia_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> IdeiaRepository:
    return IdeiaRepository(db)


@router.get("/", response_model=list[IdeiaResponse])
async def list_ideias(
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    nicho_id: UUID | None = None,
    status: str | None = None,
    origem: str | None = None,
):
    """Lista todas as ideias com filtros opcionais."""
    return await repo.list(
        skip=skip,
        limit=limit,
        nicho_id=nicho_id,
        status=status,
        origem=origem,
    )


@router.post("/", response_model=IdeiaResponse, status_code=201)
async def create_ideia(
    ideia_data: IdeiaCreate,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """Cria uma nova ideia."""
    return await repo.create(ideia_data)


@router.get("/{ideia_id}", response_model=IdeiaResponse)
async def get_ideia(
    ideia_id: UUID,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """Retorna uma ideia pelo ID."""
    ideia = await repo.get_by_id(ideia_id)
    if not ideia:
        raise HTTPException(status_code=404, detail="Ideia não encontrada")
    return ideia


@router.put("/{ideia_id}", response_model=IdeiaResponse)
async def update_ideia(
    ideia_id: UUID,
    ideia_data: IdeiaUpdate,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """Atualiza uma ideia existente."""
    ideia = await repo.update(ideia_id, ideia_data)
    if not ideia:
        raise HTTPException(status_code=404, detail="Ideia não encontrada")
    return ideia


@router.delete("/{ideia_id}", status_code=204)
async def delete_ideia(
    ideia_id: UUID,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """Remove uma ideia."""
    deleted = await repo.delete(ideia_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ideia não encontrada")
