"""
Router CRUD para a entidade Roteiro.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.roteiro_repository import RoteiroRepository
from app.schemas.roteiro import RoteiroCreate, RoteiroUpdate, RoteiroResponse


router = APIRouter(prefix="/roteiros", tags=["roteiros"])


def get_roteiro_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> RoteiroRepository:
    return RoteiroRepository(db)


@router.get("/", response_model=list[RoteiroResponse])
async def list_roteiros(
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ideia_id: UUID | None = None,
    status: str | None = None,
):
    """Lista todos os roteiros com filtros opcionais."""
    return await repo.list(
        skip=skip,
        limit=limit,
        ideia_id=ideia_id,
        status=status,
    )


@router.post("/", response_model=RoteiroResponse, status_code=201)
async def create_roteiro(
    roteiro_data: RoteiroCreate,
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
):
    """Cria um novo roteiro."""
    return await repo.create(roteiro_data)


@router.get("/{roteiro_id}", response_model=RoteiroResponse)
async def get_roteiro(
    roteiro_id: UUID,
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
):
    """Retorna um roteiro pelo ID."""
    roteiro = await repo.get_by_id(roteiro_id)
    if not roteiro:
        raise HTTPException(status_code=404, detail="Roteiro não encontrado")
    return roteiro


@router.get("/ideia/{ideia_id}/latest", response_model=RoteiroResponse)
async def get_latest_roteiro_by_ideia(
    ideia_id: UUID,
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
):
    """Retorna a versão mais recente do roteiro para uma ideia."""
    roteiro = await repo.get_latest_version_by_ideia(ideia_id)
    if not roteiro:
        raise HTTPException(
            status_code=404,
            detail="Nenhum roteiro encontrado para esta ideia"
        )
    return roteiro


@router.put("/{roteiro_id}", response_model=RoteiroResponse)
async def update_roteiro(
    roteiro_id: UUID,
    roteiro_data: RoteiroUpdate,
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
):
    """Atualiza um roteiro existente."""
    roteiro = await repo.update(roteiro_id, roteiro_data)
    if not roteiro:
        raise HTTPException(status_code=404, detail="Roteiro não encontrado")
    return roteiro


@router.delete("/{roteiro_id}", status_code=204)
async def delete_roteiro(
    roteiro_id: UUID,
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
):
    """Remove um roteiro."""
    deleted = await repo.delete(roteiro_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Roteiro não encontrado")
