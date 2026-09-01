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


@pytest.mark.parametrize("target_seconds", [300, 720, 1200])
def test_duration_contract_scales_across_five_twelve_and_twenty_minutes(
    target_seconds: int,
) -> None:
    target_words = round(_calibration().words_per_minute * target_seconds / 60)
    report = evaluate_duration(
        _blocks(target_words, duration=target_seconds),
        target_seconds=target_seconds,
        calibration=_calibration(),
        profile=get_profile("faceless_general"),
    )
    assert report["status"] in {"excellent", "acceptable"}
    assert report["revision_required"] is False


def test_materially_overlong_script_requires_compression() -> None:
    report = evaluate_duration(
        _blocks(1500, duration=300),
        target_seconds=300,
        calibration=_calibration(),
        profile=get_profile("faceless_general"),
    )
    assert report["status"] == "far_above_target"
    assert report["revision_required"] is True


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
    assert all(
        item["min_words"] < item["target_words"] < item["max_words"]
        for item in report["sections"]
    )
    assert quality["generic_hook"] is True
    assert quality["missing_section_purpose_count"] == 2
    assert quality["missing_editorial_beats_count"] == 2


def test_duration_prompt_forbids_filler_and_identifies_calibration() -> None:
    prompt = duration_budget_prompt(720, _calibration())
    assert "target_duration_seconds: 720" in prompt
    assert _calibration().identity in prompt
    assert "Never fill" in prompt


def test_editorial_diagnostics_flag_grandiosity_and_robotic_prose_as_signals() -> None:
    quality = evaluate_editorial_quality(
        [
            {
                "tipo": "abertura",
                "duracao_segundos": 60,
                "conteudo": (
                    "O universo de testes está prestes a mudar para sempre. "
                    "Essa transformação redefine completamente tudo. "
                    "Consequentemente, temos um novo padrão sem precedentes."
                ),
                "purpose": "Abrir",
                "beats": [{"key_point": "Ponto"}],
            }
        ]
    )
    assert quality["generic_hook"] is True
    assert "grandiosity_signals" in quality["issues"]
    assert "robotic_transition_signals" in quality["issues"]


def test_supported_natural_technical_explanation_is_not_falsely_flagged() -> None:
    quality = evaluate_editorial_quality(
        [
            {
                "tipo": "corpo",
                "duracao_segundos": 60,
                "conteudo": (
                    "O relatório mede a latência em milissegundos. O valor caiu de 40 para 25, "
                    "então a resposta chegou 15 milissegundos antes no teste documentado."
                ),
                "purpose": "Explicar o dado",
                "beats": [{"key_point": "Medição"}],
            }
        ]
    )
    assert "grandiosity_signals" not in quality["issues"]
    assert "robotic_transition_signals" not in quality["issues"]


def test_claim_tiers_and_music_intent_remain_structured_non_speakable_metadata() -> (
    None
):
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
                    "purpose": "Separar observação oficial de inferência.",
                    "beats": [
                        {
                            "purpose": "Mostrar a evidência",
                            "key_point": "A câmera aparece, mas a mecânica não foi confirmada.",
                            "evidence_refs": ["official-trailer"],
                            "target_words": 45,
                            "retention_role": "evidence_to_interpretation",
                        }
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
    assert output.blocos[0].beats[0].target_words == 45
    assert "investigative" not in speakable_text_from_blocks(
        [output.blocos[0].model_dump()]
    )
