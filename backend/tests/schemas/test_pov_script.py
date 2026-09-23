import copy
from uuid import uuid4

import pytest
from pydantic import ValidationError
from app.schemas.pov_script import POVScriptDocument
from app.schemas.manual_script_import import ManualScriptImportRequest
from app.schemas.roteiro import ProductionReadinessResponse
from app.production_profiles import get_profile
from app.services.manual_script_import import normalize_manual_script
from app.services.production_readiness import evaluate_production_readiness
from app.services.duration_contract import DurationCalibration


def document(locale="pt-BR"):
    return dict(
        schema_version="neovids_pov_script_v1",
        content_locale=locale,
        title="POV",
        narration={
            "blocks": [{"key": "intro", "text": "Você acorda. A cidade desperta."}]
        },
        storyboard={
            "scenes": [
                dict(
                    id="scene-1",
                    narration_anchor={
                        "block": "intro",
                        "start_text": "Você",
                        "end_text": "acorda.",
                    },
                    visual_intent="Quarto",
                    prompt="POV room",
                ),
                dict(
                    id="scene-2",
                    narration_anchor={
                        "block": "intro",
                        "start_text": "A cidade",
                        "end_text": "desperta.",
                    },
                    visual_intent="Rua",
                    prompt="POV street",
                ),
            ]
        },
    )


@pytest.mark.parametrize("locale", ["pt-BR", "en-US"])
def test_import_canonical_readiness_and_http_serialization(locale):
    req = ManualScriptImportRequest.model_validate(
        dict(ideia_id=uuid4(), source_filename="pov.json", script=document(locale))
    )
    board = req.script.canonical_storyboard()
    assert board["scenes"][0]["narration_anchor"]["start_char"] == 0
    calibration = DurationCalibration(
        version="test",
        identity="test",
        words_per_minute=120,
        chars_per_second=12,
        sample_count=0,
        source_window="test",
        generated_at=None,
        fallback=True,
        language=locale,
        voice_profile="test",
        generation_profile="test",
        production_profile="pov_storyboard",
    )
    profile = get_profile("pov_storyboard")
    normalized = normalize_manual_script(
        req.script,
        calibration=calibration,
        profile=profile,
        target_duration_seconds=None,
    )
    assert normalized.structure.content_locale == locale
    assert normalized.structure.imported_storyboard == board
    for status in ("rascunho", "aprovado"):
        result = evaluate_production_readiness(
            normalized.structure, script_status=status, profile=profile
        )
        serialized = ProductionReadinessResponse.model_validate(result).model_dump(
            mode="json"
        )
        assert serialized["status"] == (
            "ready" if status == "aprovado" else "not_ready"
        )
        assert serialized["visual"]["status"] == "not_required"
        assert serialized["storyboard"]["status"] == "ready"
    normalized.structure.blocos[0].conteudo = "Mudou"
    assert (
        evaluate_production_readiness(
            normalized.structure, script_status="aprovado", profile=profile
        )["status"]
        == "not_ready"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "locale",
        "duplicate",
        "block",
        "ambiguous",
        "outside",
        "order",
        "missing",
    ],
)
def test_invalid_import_fails_closed(mutation):
    d = document()
    scene = d["storyboard"]["scenes"][0]
    if mutation == "schema":
        d["schema_version"] = "wrong"
    if mutation == "locale":
        d["content_locale"] = "es-ES"
    if mutation == "duplicate":
        d["storyboard"]["scenes"][1]["id"] = scene["id"]
    if mutation == "block":
        scene["narration_anchor"]["block"] = "absent"
    if mutation == "ambiguous":
        d["narration"]["blocks"][0]["text"] += " Você"
    if mutation == "outside":
        scene["narration_anchor"] = {
            "block": "intro",
            "start_char": 0,
            "end_char": 9999,
        }
    if mutation == "order":
        d["storyboard"]["scenes"].reverse()
    if mutation == "missing":
        scene["narration_anchor"]["start_text"] = "missing"
    with pytest.raises(ValidationError):
        POVScriptDocument.model_validate(d)


def test_character_range_disambiguates_repeated_words_and_identity_is_stable():
    d = document()
    d["narration"]["blocks"][0]["text"] = "Você Você"
    d["storyboard"]["scenes"] = [d["storyboard"]["scenes"][0]]
    d["storyboard"]["scenes"][0]["narration_anchor"] = {
        "block": "intro",
        "start_char": 5,
        "end_char": 9,
    }
    model = POVScriptDocument.model_validate(d)
    assert (
        model.canonical_storyboard()
        == POVScriptDocument.model_validate(copy.deepcopy(d)).canonical_storyboard()
    )
