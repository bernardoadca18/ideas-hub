from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.production_profiles import get_profile
from app.services.duration_contract import (
    DurationCalibration,
    count_words,
    evaluate_duration,
)
from app.services.editorial_generation import (
    DurationMode,
    DurationTargetSource,
    GenerationStrategy,
    build_generation_plan,
    content_capacity_report,
    estimate_content_capacity,
    resolve_duration_intent,
    select_generation_strategy,
    validate_section_words,
)
from app.services.script_generation_jobs import assemble_written_sections


def _settings() -> Settings:
    return Settings(
        llm_model="standard-test",
        generation_single_pass_max_seconds=480,
        generation_staged_max_seconds=2700,
        generation_section_target_seconds=300,
        generation_chapter_target_seconds=1800,
        generation_max_sections=120,
    )


def test_profile_default_is_explicitly_resolved() -> None:
    intent = resolve_duration_intent(
        mode=DurationMode.PROFILE_DEFAULT,
        requested_target_seconds=None,
        profile=get_profile("faceless_general"),
    )
    assert intent.target_seconds == 720
    assert intent.source is DurationTargetSource.PROFILE


def test_explicit_target_wins_and_content_driven_is_deliberate() -> None:
    profile = get_profile("game_analysis")
    explicit = resolve_duration_intent(
        mode=DurationMode.EXPLICIT_TARGET,
        requested_target_seconds=5400,
        profile=profile,
    )
    open_ended = resolve_duration_intent(
        mode=DurationMode.CONTENT_DRIVEN,
        requested_target_seconds=None,
        profile=profile,
    )
    assert explicit.target_seconds == 5400
    assert explicit.source is DurationTargetSource.USER
    assert open_ended.target_seconds is None
    assert open_ended.source is DurationTargetSource.CONTENT


def test_omitted_game_target_cannot_silently_become_profile_default() -> None:
    with pytest.raises(ValueError, match="has no default target"):
        resolve_duration_intent(
            mode=DurationMode.PROFILE_DEFAULT,
            requested_target_seconds=None,
            profile=get_profile("game_analysis"),
        )


def test_target_above_profile_capacity_is_rejected() -> None:
    with pytest.raises(ValueError, match="practical maximum"):
        resolve_duration_intent(
            mode=DurationMode.EXPLICIT_TARGET,
            requested_target_seconds=20_000,
            profile=get_profile("faceless_general"),
        )


@pytest.mark.parametrize(
    ("minutes", "strategy"),
    [
        (12, GenerationStrategy.STAGED),
        (30, GenerationStrategy.STAGED),
        (60, GenerationStrategy.HIERARCHICAL_LONG_FORM),
        (120, GenerationStrategy.HIERARCHICAL_LONG_FORM),
        (180, GenerationStrategy.HIERARCHICAL_LONG_FORM),
    ],
)
def test_generation_plan_scales_without_giant_section_outputs(
    minutes: int, strategy: GenerationStrategy
) -> None:
    profile = get_profile("game_analysis")
    intent = resolve_duration_intent(
        mode=DurationMode.EXPLICIT_TARGET,
        requested_target_seconds=minutes * 60,
        profile=profile,
    )
    plan = build_generation_plan(
        intent=intent,
        words_per_minute=145,
        evidence_chars=100_000,
        config=_settings(),
    )
    assert plan.strategy is strategy
    assert (
        sum(item.target_duration_seconds or 0 for item in plan.sections) == minutes * 60
    )
    assert sum(item.target_words or 0 for item in plan.sections) == round(145 * minutes)
    assert max(item.target_duration_seconds or 0 for item in plan.sections) <= 300
    assert max(item.max_words or 0 for item in plan.sections) < 900
    assert len(plan.sections) <= 120


def test_local_section_validation_catches_half_written_output() -> None:
    intent = resolve_duration_intent(
        mode=DurationMode.EXPLICIT_TARGET,
        requested_target_seconds=720,
        profile=get_profile("faceless_general"),
    )
    section = build_generation_plan(
        intent=intent,
        words_per_minute=145,
        config=_settings(),
    ).sections[0]
    report = validate_section_words(round((section.target_words or 0) / 2), section)
    assert report["status"] == "severely_under_budget"
    assert report["revision_required"] is True


def test_945_word_gta_regression_is_not_accepted_for_twelve_minutes() -> None:
    calibration = replace(
        DurationCalibration.fallback_for(production_profile="faceless_general"),
        words_per_minute=148.0,
        chars_per_second=14.5,
    )
    # Representative speakable fixture: metadata and the seven declared labels are
    # intentionally absent because they are not narration.
    report = evaluate_duration(
        [
            {
                "tipo": f"evolucao-{index}",
                "duracao_segundos": duration,
                "conteudo": " ".join("fala" for _ in range(words)),
            }
            for index, (words, duration) in enumerate(
                zip([135] * 7, [90, 100, 100, 100, 90, 110, 100], strict=True),
                start=1,
            )
        ],
        target_seconds=720,
        calibration=calibration,
        profile=get_profile("faceless_general"),
    )
    assert report["speakable_words"] == 945
    assert report["status"] == "far_below_target"
    assert report["revision_required"] is True
    assert report["predicted_duration_seconds"] < 430


def test_content_capacity_is_advisory_but_exposes_unsustainable_target() -> None:
    report = content_capacity_report(
        evidence_claims=2,
        evidence_chars=1_000,
        target_words=18_000,
    )
    assert report["status"] == "probably_insufficient"
    assert report["advisory_only"] is True


@pytest.mark.parametrize(
    ("evidence_chars", "evidence_units", "expected_strategy"),
    [
        (5_000, 0, GenerationStrategy.SINGLE_PASS),
        (30_000, 0, GenerationStrategy.STAGED),
        (90_000, 0, GenerationStrategy.HIERARCHICAL_LONG_FORM),
        (150_000, 0, GenerationStrategy.HIERARCHICAL_LONG_FORM),
        (0, 50, GenerationStrategy.STAGED),
        (0, 150, GenerationStrategy.HIERARCHICAL_LONG_FORM),
    ],
)
def test_content_driven_strategy_uses_capacity_estimate(
    evidence_chars: int, evidence_units: int, expected_strategy: GenerationStrategy
) -> None:
    profile = get_profile("game_analysis")
    intent = resolve_duration_intent(
        mode=DurationMode.CONTENT_DRIVEN,
        requested_target_seconds=None,
        profile=profile,
    )
    strategy = select_generation_strategy(
        intent,
        evidence_chars=evidence_chars,
        evidence_units=evidence_units,
        config=_settings(),
    )
    assert strategy is expected_strategy


def test_content_capacity_estimate_scales_with_evidence() -> None:
    small = estimate_content_capacity(evidence_chars=5_000, evidence_units=0)
    medium = estimate_content_capacity(evidence_chars=50_000, evidence_units=0)
    large = estimate_content_capacity(evidence_chars=150_000, evidence_units=0)

    assert small.estimated_seconds < medium.estimated_seconds < large.estimated_seconds
    assert small.confidence == "low"
    assert medium.confidence in {"medium", "high"}
    assert large.confidence == "high"


@pytest.mark.parametrize(
    ("evidence_chars", "expected_section_range"),
    [
        (5_000, (1, 2)),
        (30_000, (3, 8)),
        (90_000, (12, 25)),
        (150_000, (20, 40)),
    ],
)
def test_content_driven_plan_scales_sections_by_capacity(
    evidence_chars: int, expected_section_range: tuple[int, int]
) -> None:
    profile = get_profile("game_analysis")
    intent = resolve_duration_intent(
        mode=DurationMode.CONTENT_DRIVEN,
        requested_target_seconds=None,
        profile=profile,
    )
    plan = build_generation_plan(
        intent=intent,
        words_per_minute=145,
        evidence_chars=evidence_chars,
        config=_settings(),
    )
    min_sections, max_sections = expected_section_range
    assert min_sections <= len(plan.sections) <= max_sections


@pytest.mark.parametrize("minutes", [30, 60, 120, 180])
def test_long_form_sections_assemble_without_a_monolithic_model_output(
    minutes: int,
) -> None:
    intent = resolve_duration_intent(
        mode=DurationMode.EXPLICIT_TARGET,
        requested_target_seconds=minutes * 60,
        profile=get_profile("game_analysis"),
    )
    plan = build_generation_plan(
        intent=intent,
        words_per_minute=145,
        evidence_chars=200_000,
        config=_settings(),
    )
    sections = []
    for budget in plan.sections:
        content = " ".join("fala" for _ in range(budget.target_words or 100))
        sections.append(
            SimpleNamespace(
                section_key=budget.key,
                section_order=budget.order,
                section_plan={
                    "title": budget.key,
                    "target_duration_seconds": budget.target_duration_seconds,
                    "purpose": "progressão",
                    "beats": ["evidência", "interpretação", "transição"],
                    "evidence_refs": [],
                },
                output={
                    "content": content,
                    "claims_used": [],
                    "visual_intent": None,
                    "audio_intent": None,
                },
            )
        )
    blocks = assemble_written_sections(sections, claim_ledger=[])
    assert len(blocks) == len(plan.sections)
    assert sum(count_words(block.conteudo) for block in blocks) == plan.target_words
    assert max(count_words(block.conteudo) for block in blocks) < 900
