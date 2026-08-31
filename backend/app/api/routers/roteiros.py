"""
Router CRUD para a entidade Roteiro.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.roteiro_repository import RoteiroRepository
from app.schemas.analise_jogo import AnaliseJogoRequest, AnaliseJogoResponse
from app.schemas.roteiro import (
    RoteiroResponse,
    ScriptCreateRequest,
    ScriptEditRevisionRequest,
    ScriptRegenerationRequest,
)

router = APIRouter(prefix="/roteiros", tags=["roteiros"])


def get_roteiro_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> RoteiroRepository:
    return RoteiroRepository(db)


@router.get("/", response_model=list[RoteiroResponse])
async def list_roteiros(
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ideia_id: UUID | None = None,
    status: str | None = None,
):
    """
    Lista todos os roteiros com filtros opcionais.

    Use status=aprovado para listar roteiros prontos para produção.
    """
    return await repo.list(
        skip=skip,
        limit=limit,
        ideia_id=ideia_id,
        status=status,
    )


@router.post("/", response_model=RoteiroResponse, status_code=201)
async def create_roteiro(
    roteiro_data: ScriptCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a versioned draft while keeping snapshot/provenance server-owned."""
    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        return await get_roteiro_generator(db).create_manual_draft(
            roteiro_data.ideia_id, roteiro_data.estrutura
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{roteiro_id:uuid}", response_model=RoteiroResponse)
async def get_roteiro(
    roteiro_id: UUID,
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
):
    """Retorna um roteiro pelo ID."""
    roteiro = await repo.get_by_id(roteiro_id)
    if not roteiro:
        raise HTTPException(status_code=404, detail="Roteiro não encontrado")
    return roteiro


@router.get("/{roteiro_id:uuid}/duration")
async def get_duration_contract(
    roteiro_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Re-evaluate speakable duration against the current calibration snapshot."""

    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        return await get_roteiro_generator(db).duration_report(roteiro_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ideia/{ideia_id}/latest", response_model=RoteiroResponse)
async def get_latest_roteiro_by_ideia(
    ideia_id: UUID,
    repo: Annotated[RoteiroRepository, Depends(get_roteiro_repo)],
):
    """Retorna a versão mais recente do roteiro para uma ideia."""
    roteiro = await repo.get_latest_version_by_ideia(ideia_id)
    if not roteiro:
        raise HTTPException(
            status_code=404, detail="Nenhum roteiro encontrado para esta ideia"
        )
    return roteiro


@router.put("/{roteiro_id:uuid}", response_model=RoteiroResponse)
async def update_roteiro(
    roteiro_id: UUID,
    roteiro_data: dict,
):
    """Deprecated mutation boundary: scripts are revised, never overwritten."""
    raise HTTPException(
        status_code=409,
        detail=(
            "Roteiros são versionados e não podem ser sobrescritos. "
            "Use POST /roteiros/{id}/revisoes/editar."
        ),
    )


@router.delete("/{roteiro_id:uuid}", status_code=204)
async def delete_roteiro(
    roteiro_id: UUID,
):
    """Scripts form an audit history and are not physically deleted through the API."""
    raise HTTPException(
        status_code=409, detail="O histórico de versões de roteiro é imutável."
    )


@router.post(
    "/{roteiro_id:uuid}/revisoes/editar",
    response_model=RoteiroResponse,
    status_code=201,
)
async def editar_como_nova_revisao(
    roteiro_id: UUID,
    payload: ScriptEditRevisionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a human-edited version while preserving VisualQuery provenance."""

    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        created = await get_roteiro_generator(db).create_human_edit_revision(
            roteiro_id, payload
        )
        refreshed = await RoteiroRepository(db).get_by_id(created.id)
        assert refreshed is not None
        return refreshed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{roteiro_id:uuid}/revisoes/regenerar",
    response_model=RoteiroResponse,
    status_code=201,
)
async def regenerar_com_feedback(
    roteiro_id: UUID,
    payload: ScriptRegenerationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Generate a new version from explicit operator feedback."""

    from app.services.roteiros.gerador_roteiro import (
        ScriptGenerationError,
        get_roteiro_generator,
    )

    try:
        created = await get_roteiro_generator(db).regenerate_with_feedback(
            roteiro_id, payload.feedback
        )
        refreshed = await RoteiroRepository(db).get_by_id(created.id)
        assert refreshed is not None
        return refreshed
    except ScriptGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail={"category": exc.category, "message": exc.public_message},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{roteiro_id:uuid}/aprovar", response_model=RoteiroResponse)
async def aprovar_roteiro(
    roteiro_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Aprova um roteiro.

    Roteiros aprovados ficam prontos para produção.
    A ideia vinculada muda para status "roteirizada".
    """
    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    generator = get_roteiro_generator(db)
    try:
        await generator.aprovar_roteiro(roteiro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Recarrega para retornar objeto completo
    repo = RoteiroRepository(db)
    roteiro = await repo.get_by_id(roteiro_id)
    return roteiro


@router.patch("/{roteiro_id:uuid}/rejeitar", response_model=RoteiroResponse)
async def rejeitar_roteiro(
    roteiro_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Rejeita um roteiro.

    A ideia vinculada volta para status "aprovada" para gerar novo roteiro.
    """
    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    generator = get_roteiro_generator(db)
    try:
        await generator.rejeitar_roteiro(roteiro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Recarrega para retornar objeto completo
    repo = RoteiroRepository(db)
    roteiro = await repo.get_by_id(roteiro_id)
    return roteiro


@router.post("/analise-jogo", response_model=AnaliseJogoResponse, status_code=201)
async def criar_analise_de_jogo(
    request: AnaliseJogoRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Workflow de Análise de Jogos: recebe as anotações de gameplay do autor e gera
    diretamente uma Ideia (já aprovada) + Roteiro v1, fora do funil de trends.
    """
    from app.services.roteiros.gerador_roteiro import (
        ScriptGenerationError,
        get_roteiro_generator,
    )

    generator = get_roteiro_generator(db)
    try:
        resultado = await generator.generate_from_notas(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ScriptGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail={"category": exc.category, "message": exc.public_message},
        ) from exc
    return resultado
