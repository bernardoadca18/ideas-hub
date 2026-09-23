"""Durable script generation API; long-form work never holds the request open."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.production_profiles import get_profile, is_valid_profile_id, list_profiles
from app.schemas.generation import (
    GameGenerationRunCreate,
    GenerationPreviewRequest,
    GenerationRunCreate,
    GenerationRunResponse,
    ManualDraftImprovementRunCreate,
    ManualDraftImprovementRunResponse,
    RevisionGenerationRunCreate,
)
from app.services.duration_contract import duration_calibration_client
from app.services.editorial_generation import (
    build_generation_plan,
    content_capacity_report,
    resolve_duration_intent,
)
from app.services.script_generation_jobs import ScriptGenerationJobService

router = APIRouter(tags=["script-generation"])


@router.get("/editorial/production-profiles")
async def production_profiles():
    from dataclasses import asdict

    return [
        {
            "id": profile.id,
            "name": profile.nome,
            "description": profile.descricao,
            "capabilities": asdict(profile.capabilities),
            "duration_policy": {
                "preferred_min_seconds": profile.duracao.target_min_seconds,
                "preferred_max_seconds": profile.duracao.target_max_seconds,
                "default_target_seconds": profile.duracao.default_target_seconds,
                "content_driven_allowed": profile.duracao.content_driven_allowed,
                "max_practical_duration_seconds": profile.max_practical_duration_seconds,
            },
            "generation_strategy": profile.generation_strategy,
            "research_strategy": profile.research_strategy,
            "model_routing_policy": profile.model_routing_policy,
            "long_form_supported": profile.long_form_supported,
            "visual_requirements": {
                "target_beat_seconds": profile.visual_requirements.target_beat_seconds,
                "max_beats_per_llm_call": (
                    profile.visual_requirements.max_beats_per_llm_call
                ),
                "requires_visual_queries_for_final": (
                    profile.visual_requirements.requires_visual_queries_for_final
                ),
                "version": profile.visual_requirements.version,
                "identity": profile.visual_requirements.identity,
            },
        }
        for profile in list_profiles()
    ]


@router.post("/editorial/generation-preview")
async def generation_preview(payload: GenerationPreviewRequest):
    if not is_valid_profile_id(payload.production_profile):
        raise HTTPException(status_code=422, detail="unknown production profile")
    profile = get_profile(payload.production_profile)
    intent = resolve_duration_intent(
        mode=payload.duration_mode,
        requested_target_seconds=payload.target_duration_seconds,
        profile=profile,
    )
    calibration = await duration_calibration_client.get(
        profile.id, payload.content_locale
    )
    plan = build_generation_plan(
        intent=intent,
        words_per_minute=calibration.words_per_minute,
        evidence_chars=payload.evidence_chars,
    )
    return {
        "duration_intent": intent.to_dict(),
        "strategy": plan.strategy.value,
        "strategy_version": plan.strategy_version,
        "strategy_identity": plan.identity,
        "target_words": plan.target_words,
        "chapter_count": plan.chapter_count,
        "section_count": len(plan.sections),
        "estimated_llm_calls": 1 + len(plan.sections),
        "calibration_identity": calibration.identity,
        "content_capacity": content_capacity_report(
            evidence_claims=0,
            evidence_chars=payload.evidence_chars,
            target_words=plan.target_words,
        ),
        "sections": [
            {
                "key": item.key,
                "chapter_order": item.chapter_order,
                "target_duration_seconds": item.target_duration_seconds,
                "target_words": item.target_words,
                "min_words": item.min_words,
                "max_words": item.max_words,
            }
            for item in plan.sections
        ],
    }


@router.post(
    "/ideias/{ideia_id}/generation-runs",
    response_model=GenerationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_generation_run(
    ideia_id: UUID,
    payload: GenerationRunCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await ScriptGenerationJobService(db).enqueue(
            ideia_id,
            idempotency_key=payload.idempotency_key,
            model_strategy=payload.model_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/ideias/{ideia_id}/manual-draft-improvement-runs",
    response_model=ManualDraftImprovementRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_manual_draft_improvement_run(
    ideia_id: UUID,
    payload: ManualDraftImprovementRunCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Persist pasted human prose and enqueue its immutable V3 child revision."""

    try:
        return await ScriptGenerationJobService(db).enqueue_manual_draft_improvement(
            ideia_id,
            draft_text=payload.draft_text,
            content_locale=payload.content_locale,
            idempotency_key=payload.idempotency_key,
            feedback=payload.feedback,
            model_strategy=payload.model_strategy,
        )
    except ValueError as exc:
        status_code = 404 if str(exc) == "Ideia não encontrada" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post(
    "/roteiros/{roteiro_id}/generation-runs",
    response_model=GenerationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_revision_generation_run(
    roteiro_id: UUID,
    payload: RevisionGenerationRunCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Revise through durable V3 diagnostics plus optional operator direction."""

    try:
        return await ScriptGenerationJobService(db).enqueue_revision(
            roteiro_id,
            idempotency_key=payload.idempotency_key,
            feedback=payload.feedback,
            model_strategy=payload.model_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/roteiros/{roteiro_id}/audit",
    response_model=GenerationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_reaudit_run(
    roteiro_id: UUID,
    payload: GenerationRunCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Audit current narration without invoking the WRITING role."""

    try:
        return await ScriptGenerationJobService(db).enqueue_reaudit(
            roteiro_id,
            idempotency_key=payload.idempotency_key,
            model_strategy=payload.model_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/editorial/game-analysis/generation-runs",
    response_model=GenerationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_game_generation_run(
    payload: GameGenerationRunCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await ScriptGenerationJobService(db).enqueue_game_analysis(
            payload,
            idempotency_key=payload.idempotency_key,
            model_strategy=payload.model_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/generation-runs/{run_id}", response_model=GenerationRunResponse)
async def get_generation_run(
    run_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    run = await ScriptGenerationJobService(db).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="generation run not found")
    return run


@router.get("/generation-runs", response_model=list[GenerationRunResponse])
async def list_generation_runs(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    run_status: str | None = None,
):
    return await ScriptGenerationJobService(db).list_recent(
        limit=limit,
        status=run_status,
    )


@router.post("/generation-runs/{run_id}/resume", response_model=GenerationRunResponse)
async def resume_generation_run(
    run_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await ScriptGenerationJobService(db).resume(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/generation-runs/{run_id}/cancel", response_model=GenerationRunResponse)
async def cancel_generation_run(
    run_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await ScriptGenerationJobService(db).cancel(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
