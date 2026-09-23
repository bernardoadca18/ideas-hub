"""The first real non-video production profile."""

import pytest

from app.production_profiles import get_profile, is_valid_profile_id
from app.schemas.roteiro import RoteiroEstrutura
from app.services.production_readiness import evaluate_production_readiness


@pytest.mark.parametrize("locale", ["pt-BR", "en-US"])
def test_gamedev_manual_is_ready_without_visuals_or_media(locale):
    assert is_valid_profile_id("gamedev_manual")
    profile = get_profile("gamedev_manual")
    assert profile.capabilities.delivery_mode == "manual_edit_package"
    assert profile.capabilities.visual_mode == "none"
    assert profile.capabilities.requires_media_scope is False
    assert profile.capabilities.caption_policy == "none"
    structure = RoteiroEstrutura.model_validate(
        {
            "content_locale": locale,
            "titulo": "Experimento de IA",
            "duracao_total_segundos": 20,
            "blocos": [
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": 20,
                    "conteudo": "Hoje criei uma IA para meus NPCs.",
                    "visual_queries": [],
                }
            ],
        }
    )
    report = evaluate_production_readiness(
        structure, script_status="aprovado", profile=profile
    )
    assert report["status"] == "ready"
    assert report["visual"]["status"] == "not_required"
    assert report["media_scope"]["status"] == "not_required"
    assert report["capabilities"]["delivery_mode"] == "manual_edit_package"


@pytest.mark.parametrize("locale", ["pt-BR", "en-US"])
def test_manual_import_normalizes_real_gamedev_profile(locale):
    from app.schemas.manual_script_import import ManualScriptDocument
    from app.services.duration_contract import DurationCalibration
    from app.services.manual_script_import import normalize_manual_script

    document = ManualScriptDocument.model_validate(
        {
            "schema": "neovids_manual_script_v1",
            "title": "Polícia de GTA IV",
            "blocks": [{"type": "abertura", "text": "Hoje recriei a polícia do zero."}],
        }
    )
    calibration = DurationCalibration(
        version="test-v1",
        identity="test",
        words_per_minute=120,
        chars_per_second=12,
        sample_count=0,
        source_window="tests",
        generated_at=None,
        fallback=True,
        language=locale,
        voice_profile="test",
        generation_profile="test",
        production_profile="gamedev_manual",
    )
    normalized = normalize_manual_script(
        document,
        calibration=calibration,
        profile=get_profile("gamedev_manual"),
        target_duration_seconds=None,
        content_locale=locale,
    )
    assert normalized.structure.content_locale == locale
    assert normalized.structure.blocos[0].visual_queries == []
    assert normalized.structure.media_context is None
    report = evaluate_production_readiness(
        normalized.structure,
        script_status="aprovado",
        profile=get_profile("gamedev_manual"),
    )
    assert report["status"] == "ready"
