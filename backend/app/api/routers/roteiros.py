"""
Router CRUD para a entidade Roteiro.
"""

import hashlib
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.roteiro_repository import RoteiroRepository
from app.schemas.analise_jogo import AnaliseJogoRequest
from app.schemas.generation import GenerationRunResponse
from app.schemas.manual_script_import import (
    ManualScriptImportPreviewResponse,
    ManualScriptImportRequest,
    ManualScriptImportResponse,
)
from app.schemas.roteiro import (
    MediaBindingRequest,
    ProductionReadinessResponse,
    RoteiroResponse,
    ScriptCreateRequest,
    ScriptEditRevisionRequest,
    ScriptRegenerationRequest,
    VisualQueryRepairRequest,
    VisualReadinessResponse,
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


@router.post(
    "/importar/preview",
    response_model=ManualScriptImportPreviewResponse,
)
async def preview_manual_script_import(
    payload: ManualScriptImportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Validate and normalize a manual JSON file without persisting anything."""

    from app.services.manual_script_import import (
        ManualMediaScopeError,
        ManualMediaScopeUnavailableError,
    )
    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        return await get_roteiro_generator(db).preview_manual_import(payload)
    except ManualMediaScopeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ManualMediaScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if str(exc) == "Ideia não encontrada" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post(
    "/importar",
    response_model=ManualScriptImportResponse,
    status_code=201,
)
async def import_manual_script(
    payload: ManualScriptImportRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create an idempotent canonical draft and optional media-binding revision."""

    from app.services.manual_script_import import (
        ManualMediaScopeError,
        ManualMediaScopeUnavailableError,
    )
    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        result = await get_roteiro_generator(db).import_manual_script(payload)
    except ManualMediaScopeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ManualMediaScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if str(exc) == "Ideia não encontrada" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if not result.created:
        response.status_code = 200
    return result


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


@router.get(
    "/{roteiro_id:uuid}/visual-readiness",
    response_model=VisualReadinessResponse,
)
async def get_visual_readiness(
    roteiro_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Compute canonical visual-structure readiness without mutating history."""

    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        return await get_roteiro_generator(db).visual_readiness_report(roteiro_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{roteiro_id:uuid}/production-readiness",
    response_model=ProductionReadinessResponse,
)
async def get_production_readiness(
    roteiro_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Compose editorial, visual, and profile-owned media prerequisites."""

    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        return await get_roteiro_generator(db).production_readiness_report(roteiro_id)
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
    "/{roteiro_id:uuid}/revisoes/vincular-midia",
    response_model=RoteiroResponse,
    status_code=201,
)
async def vincular_midia_como_nova_revisao(
    roteiro_id: UUID,
    payload: MediaBindingRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Bind a structurally validated Media Indexer scope in an immutable draft."""

    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        created = await get_roteiro_generator(db).bind_media_context_revision(
            roteiro_id, payload
        )
        refreshed = await RoteiroRepository(db).get_by_id(created.id)
        assert refreshed is not None
        return refreshed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{roteiro_id:uuid}/revisoes/reparar-visual-queries",
    response_model=RoteiroResponse,
    status_code=201,
)
async def reparar_visual_queries_como_nova_revisao(
    roteiro_id: UUID,
    payload: VisualQueryRepairRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Repair selected VisualQuery text without rewriting narration or spans."""

    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        created = await get_roteiro_generator(db).repair_visual_queries_revision(
            roteiro_id, payload
        )
        refreshed = await RoteiroRepository(db).get_by_id(created.id)
        assert refreshed is not None
        return refreshed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{roteiro_id:uuid}/preparar-producao",
    response_model=RoteiroResponse,
    status_code=201,
)
async def preparar_para_producao(
    roteiro_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create an immutable visual-enrichment revision for a compatible script.

    The host owns deterministic coverage beats; bounded LLM calls describe what
    footage to search for and cannot modify narration or coverage spans.
    """
    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    try:
        created = await get_roteiro_generator(db).create_visual_enrichment_revision(
            roteiro_id
        )
        refreshed = await RoteiroRepository(db).get_by_id(created.id)
        assert refreshed is not None
        return refreshed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{roteiro_id:uuid}/revisoes/regenerar",
    response_model=GenerationRunResponse,
    status_code=202,
)
async def regenerar_com_feedback(
    roteiro_id: UUID,
    payload: ScriptRegenerationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Compatibility boundary delegating regeneration to durable Editorial V3."""

    from app.services.script_generation_jobs import ScriptGenerationJobService

    try:
        fallback_key = (
            "legacy-revision-"
            + hashlib.sha256(
                f"{roteiro_id}:{payload.feedback or ''}".encode()
            ).hexdigest()
        )
        return await ScriptGenerationJobService(db).enqueue_revision(
            roteiro_id,
            idempotency_key=payload.idempotency_key or fallback_key,
            feedback=payload.feedback,
            model_strategy=payload.model_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


@router.post("/analise-jogo", response_model=GenerationRunResponse, status_code=202)
async def criar_analise_de_jogo(
    request: AnaliseJogoRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Compatibility endpoint delegating game analysis to durable Editorial V3.
    """
    from app.services.script_generation_jobs import ScriptGenerationJobService

    try:
        return await ScriptGenerationJobService(db).enqueue_game_analysis(
            request,
            idempotency_key=f"legacy-game-analysis-{uuid4()}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
