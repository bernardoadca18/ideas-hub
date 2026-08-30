from __future__ import annotations

from dataclasses import replace

import pytest
from app.production_profiles import get_profile
from app.schemas.llm_outputs import EvidenceTier, ScriptLLMOutput
from app.services.duration_contract import (
    DurationCalibration,
    duration_budget_prompt,
    evaluate_duration,
    evaluate_editorial_quality,
    speakable_text_from_blocks,
)


def _calibration() -> DurationCalibration:
    return DurationCalibration.fallback_for(production_profile="faceless_general")


def _blocks(words: int, *, duration: int = 720) -> list[dict]:
    # Five-letter tokens approximate the observed PT-BR narration char/word ratio.
    content = " ".join("audio" for _ in range(words))
    return [
        {
            "tipo": "desenvolvimento",
            "duracao_segundos": duration,
            "conteudo": content,
            "dicas_visual": "metadata excluded",
            "dicas_audio": "music intent excluded",
        }
    ]


def test_twelve_minute_target_with_six_minute_script_requires_revision() -> None:
    report = evaluate_duration(
        _blocks(860),
        target_seconds=720,
        calibration=_calibration(),
        profile=get_profile("faceless_general"),
    )
    assert report["predicted_duration_seconds"] == pytest.approx(360, abs=12)
    assert report["status"] == "far_below_target"
    assert report["revision_required"] is True


def test_twelve_minute_target_near_eleven_thirty_is_acceptable() -> None:
    report = evaluate_duration(
        _blocks(1667),
        target_seconds=720,
        calibration=_calibration(),
        profile=get_profile("faceless_general"),
    )
    assert report["predicted_duration_seconds"] == pytest.approx(690, abs=15)
    assert report["status"] in {"excellent", "acceptable"}
    assert report["revision_required"] is False


def test_no_target_is_estimate_only() -> None:
    report = evaluate_duration(
        _blocks(500),
        target_seconds=None,
        calibration=_calibration(),
        profile=get_profile("game_analysis"),
    )
    assert report["status"] == "estimate_only"
    assert report["revision_required"] is False


def test_calibration_identity_and_rate_change_estimate_deterministically() -> None:
    initial = _calibration()
    slower = replace(initial, identity="calibration-b", words_per_minute=120.0)
    first = evaluate_duration(
        _blocks(600),
        target_seconds=300,
        calibration=initial,
        profile=get_profile("faceless_general"),
    )
    second = evaluate_duration(
        _blocks(600),
        target_seconds=300,
        calibration=slower,
        profile=get_profile("faceless_general"),
    )
    assert second["predicted_duration_seconds"] > first["predicted_duration_seconds"]
    assert first["identity"] != second["identity"]


def test_speakable_text_excludes_titles_visual_audio_and_music_metadata() -> None:
    blocks = _blocks(10)
    text = speakable_text_from_blocks(blocks)
    assert "metadata excluded" not in text
    assert "music intent excluded" not in text
    assert len(text.split()) == 10


def test_section_budgets_and_editorial_diagnostics_are_deterministic() -> None:
    blocks = [
        {
            "tipo": "abertura",
            "duracao_segundos": 120,
            "conteudo": "Hoje vamos falar " + "a " * 250,
        },
        {"tipo": "desenvolvimento", "duracao_segundos": 600, "conteudo": "b " * 1400},
    ]
    report = evaluate_duration(
        blocks,
        target_seconds=720,
        calibration=_calibration(),
        profile=get_profile("faceless_general"),
    )
    quality = evaluate_editorial_quality(blocks)
    assert len(report["sections"]) == 2
    assert sum(item["target_duration_seconds"] for item in report["sections"]) == 720
    assert quality["generic_hook"] is True


def test_duration_prompt_forbids_filler_and_identifies_calibration() -> None:
    prompt = duration_budget_prompt(720, _calibration())
    assert "target_duration_seconds: 720" in prompt
    assert _calibration().identity in prompt
    assert "Never fill" in prompt


def test_claim_tiers_and_music_intent_remain_structured_non_speakable_metadata() -> None:
    output = ScriptLLMOutput.model_validate(
        {
            "titulo": "Observação não é confirmação",
            "duracao_total_segundos": 60,
            "blocos": [
                {
                    "tipo": "abertura",
                    "duracao_segundos": 60,
                    "conteudo": "Uma câmera aparece no material oficial.",
                    "claims": [
                        {
                            "summary": "Uma câmera aparece no trailer.",
                            "evidence_tier": "official_observation",
                            "source_identity": "official-trailer",
                            "confidence": 1.0,
                        },
                        {
                            "summary": "Pode representar uma mecânica.",
                            "evidence_tier": "inference",
                            "source_identity": "official-trailer",
                            "confidence": 0.5,
                        },
                    ],
                    "audio_intent": {
                        "music_enabled": True,
                        "moods": ["investigative"],
                        "energy": 0.4,
                        "styles": ["electronic"],
                        "vocals": False,
                        "sfx_intent": [],
                    },
                }
            ],
            "tags": [],
        }
    )
    assert output.blocos[0].claims[0].evidence_tier is EvidenceTier.official_observation
    assert output.blocos[0].claims[1].evidence_tier is EvidenceTier.inference
    assert "investigative" not in speakable_text_from_blocks(
        [output.blocos[0].model_dump()]
    )
