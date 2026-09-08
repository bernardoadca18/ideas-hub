"""Profile-aware composition of editorial, visual, and media-scope readiness."""

from __future__ import annotations

from typing import Any

from app.production_profiles import ProductionProfile
from app.schemas.roteiro import RoteiroEstrutura
from app.services.visual_requirements import validate_visual_readiness


def evaluate_production_readiness(
    structure: RoteiroEstrutura,
    *,
    script_status: str,
    profile: ProductionProfile,
) -> dict[str, Any]:
    visual = validate_visual_readiness(structure, profile.visual_requirements)
    issues: list[dict[str, Any]] = []
    if script_status != "aprovado":
        issues.append({"code": "editorial_approval_missing"})
    if visual.status != "ready":
        issues.append({"code": "visual_readiness_not_ready"})

    context = structure.media_context
    if profile.requires_media_scope and context is None:
        media_status = "missing"
        issues.append({"code": "media_scope_missing"})
    elif context is None:
        media_status = "not_required"
    else:
        media_status = "ready"

    return {
        "status": "ready" if not issues else "not_ready",
        "profile": profile.id,
        "editorial_status": script_status,
        "visual": visual.to_dict(),
        "media_scope": {
            "required": profile.requires_media_scope,
            "status": media_status,
            "media_project_id": str(context.media_project_id) if context else None,
            "media_session_ids": (
                [str(value) for value in context.media_session_ids] if context else []
            ),
        },
        "issues": issues,
    }
