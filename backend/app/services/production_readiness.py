"""Profile-aware composition of editorial, visual, and media-scope readiness."""

from __future__ import annotations

from typing import Any
from dataclasses import asdict

from app.production_profiles import ProductionProfile
from app.schemas.roteiro import RoteiroEstrutura
from app.services.visual_requirements import validate_visual_readiness


def evaluate_production_readiness(
    structure: RoteiroEstrutura,
    *,
    script_status: str,
    profile: ProductionProfile,
) -> dict[str, Any]:
    capabilities = profile.capabilities
    visual_required = (
        capabilities.delivery_mode == "rendered_video"
        and capabilities.visual_mode == "semantic_match"
    )
    visual = (
        validate_visual_readiness(structure, profile.visual_requirements)
        if visual_required
        else None
    )
    issues: list[dict[str, Any]] = []
    if script_status != "aprovado":
        issues.append({"code": "editorial_approval_missing"})
    if visual is not None and visual.status != "ready":
        issues.append({"code": "visual_readiness_not_ready"})

    storyboard_gate = None
    if capabilities.visual_mode == "storyboard":
        from app.schemas.pov_script import POVScriptDocument
        imported = getattr(structure, "imported_storyboard", None)
        storyboard_gate = {"status": "not_ready", "required": True}
        try:
            if not isinstance(imported, dict):
                raise ValueError("storyboard_missing")
            scenes = []
            for scene in imported["scenes"]:
                anchor = scene["narration_anchor"]
                scenes.append({**scene, "narration_anchor": {
                    k: anchor[k] for k in ("block", "start_char", "end_char")
                }})
            document = POVScriptDocument.model_validate({
                "schema_version": "neovids_pov_script_v1",
                "content_locale": structure.content_locale, "title": structure.titulo,
                "narration": {"blocks": [{"key": b.tipo, "text": b.conteudo} for b in structure.blocos]},
                "storyboard": {"style": imported["style"], "continuity": imported["continuity"], "scenes": scenes},
            })
            if document.canonical_storyboard() != imported:
                raise ValueError("storyboard_anchor_invalid")
            storyboard_gate.update(status="ready", identity=imported["identity"], scene_count=len(scenes))
        except (ValueError, KeyError, TypeError):
            issues.append({"code": "storyboard_missing" if not imported else "storyboard_anchor_invalid"})

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
        "capabilities": asdict(capabilities),
        "editorial_status": script_status,
        "storyboard": storyboard_gate,
        "visual": (
            {**visual.to_dict(), "required": True, "mode": capabilities.visual_mode}
            if visual is not None
            else {
                "required": False,
                "mode": capabilities.visual_mode,
                "status": "not_required",
            }
        ),
        "media_scope": {
            "required": profile.requires_media_scope,
            "status": media_status,
            "media_project_id": str(context.media_project_id) if context else None,
            "media_session_ids": (
                [str(value) for value in context.media_session_ids] if context else []
            ),
            "static_images": (
                context.static_images.model_dump(mode="json")
                if context and context.static_images
                else {
                    "enabled": False,
                    "asset_classes": [],
                    "collections": [],
                    "source_owners": [],
                    "source_classes": [],
                }
            ),
        },
        "issues": issues,
    }
