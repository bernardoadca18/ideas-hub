"""
Router CRUD para a entidade Nicho.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.nicho_repository import NichoRepository
from app.schemas.nicho import NichoCreate, NichoUpdate, NichoResponse


router = APIRouter(prefix="/nichos", tags=["nichos"])


def get_nicho_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> NichoRepository:
    return NichoRepository(db)


@router.get("/", response_model=list[NichoResponse])
async def list_nichos(
    repo: Annotated[NichoRepository, Depends(get_nicho_repo)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ativo: bool | None = None,
):
    """Lista todos os nichos com filtros opcionais."""
    return await repo.list(skip=skip, limit=limit, ativo=ativo)


@router.post("/", response_model=NichoResponse, status_code=201)
async def create_nicho(
    nicho_data: NichoCreate,
    repo: Annotated[NichoRepository, Depends(get_nicho_repo)],
):
    """Cria um novo nicho."""
    # Verifica se slug já existe
    existing = await repo.get_by_slug(nicho_data.slug)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Nicho com slug '{nicho_data.slug}' já existe"
        )
    return await repo.create(nicho_data)


@router.get("/{nicho_id}", response_model=NichoResponse)
async def get_nicho(
    nicho_id: UUID,
    repo: Annotated[NichoRepository, Depends(get_nicho_repo)],
):
    """Retorna um nicho pelo ID."""
    nicho = await repo.get_by_id(nicho_id)
    if not nicho:
        raise HTTPException(status_code=404, detail="Nicho não encontrado")
    return nicho


@router.put("/{nicho_id}", response_model=NichoResponse)
async def update_nicho(
    nicho_id: UUID,
    nicho_data: NichoUpdate,
    repo: Annotated[NichoRepository, Depends(get_nicho_repo)],
):
    """Atualiza um nicho existente."""
    nicho = await repo.update(nicho_id, nicho_data)
    if not nicho:
        raise HTTPException(status_code=404, detail="Nicho não encontrado")
    return nicho


@router.delete("/{nicho_id}", status_code=204)
async def delete_nicho(
    nicho_id: UUID,
    repo: Annotated[NichoRepository, Depends(get_nicho_repo)],
):
    """Remove um nicho."""
    deleted = await repo.delete(nicho_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Nicho não encontrado")
