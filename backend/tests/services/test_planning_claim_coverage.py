from __future__ import annotations

import pytest
from app.schemas.generation import (
    PlannedClaimOutput,
    PlannedSectionBatchOutput,
    PlannedSectionV2Output,
)
from app.services.planning_claim_coverage import (
    validate_and_normalize_section_coverage,
)


def _claim(
    claim_id: str = "claim-a",
    *,
    source_ref: str = "source-a",
    status: str = "reported",
) -> PlannedClaimOutput:
    return PlannedClaimOutput(
        id=claim_id,
        summary="Uma fonte relata um detalhe delimitado.",
        evidence_tier="reliable_secondary",
        source_refs=[source_ref],
        confidence=0.8,
        source_trust="reliable_secondary",
        claim_status=status,
        qualification="Segundo a fonte, o detalhe foi relatado.",
        support_scope="Somente o detalhe explicitamente relatado.",
    )


def _section(
    *,
    beats: list[dict[str, object]],
) -> PlannedSectionV2Output:
    return PlannedSectionV2Output.model_validate(
        {
            "key": "section-001",
            "title": "Seção",
            "purpose": "Organizar os claims sem criar fatos.",
            "narrative_role": "desenvolvimento",
            "beat_contracts": beats,
            "must_not_repeat": [],
            "transition_target": None,
        }
    )


def _validate(
    section: PlannedSectionV2Output,
    *,
    claims: list[PlannedClaimOutput] | None = None,
):
    return validate_and_normalize_section_coverage(
        [section],
        claim_ledger=claims or [],
        known_source_ids={"source-a", "source-b"},
        grounding_required=True,
        planning_version="fragmented_editorial_planning_v2",
    )


def test_claim_backed_beat_without_claim_is_rejected() -> None:
    result = _validate(
        _section(
            beats=[
                {
                    "editorial_goal": "Afirmar um detalhe material.",
                    "kind": "claim_backed",
                    "claim_refs": [],
                    "required": True,
                }
            ]
        ),
        claims=[_claim()],
    )

    assert result.sections == {}
    assert [issue.code for issue in result.issues_by_section["section-001"]] == [
        "orphan_factual_beat",
        "grounded_section_without_claims",
    ]


def test_unknown_claim_is_rejected_before_writing() -> None:
    result = _validate(
        _section(
            beats=[
                {
                    "editorial_goal": "Usar um claim inventado.",
                    "kind": "claim_backed",
                    "claim_refs": ["claim-inventado"],
                    "required": True,
                }
            ]
        ),
        claims=[_claim()],
    )

    assert result.sections == {}
    assert any(
        issue.code == "unknown_claim_ref"
        for issue in result.issues_by_section["section-001"]
    )


def test_valid_claim_refs_derive_section_claims_evidence_and_must_cover() -> None:
    result = _validate(
        _section(
            beats=[
                {
                    "editorial_goal": "Relatar o primeiro detalhe com atribuição.",
                    "kind": "claim_backed",
                    "claim_refs": ["claim-b", "claim-a"],
                    "required": True,
                },
                {
                    "editorial_goal": "Fazer uma transição sem novo fato.",
                    "kind": "editorial",
                    "claim_refs": [],
                    "required": False,
                },
                {
                    "editorial_goal": "Retomar o primeiro claim sem duplicar refs.",
                    "kind": "claim_backed",
                    "claim_refs": ["claim-a"],
                    "required": False,
                },
            ]
        ),
        claims=[_claim("claim-a"), _claim("claim-b", source_ref="source-b")],
    )

    assert result.issues_by_section == {}
    normalized = result.sections["section-001"]
    assert normalized.claim_refs == ["claim-b", "claim-a"]
    assert normalized.evidence_refs == ["source-b", "source-a"]
    assert normalized.must_cover == ["Relatar o primeiro detalhe com atribuição."]
    assert normalized.beats == [
        "Relatar o primeiro detalhe com atribuição.",
        "Fazer uma transição sem novo fato.",
        "Retomar o primeiro claim sem duplicar refs.",
    ]


def test_editorial_beat_without_claim_is_allowed_but_not_evidence() -> None:
    result = _validate(
        _section(
            beats=[
                {
                    "editorial_goal": "Abrir com uma pergunta retórica.",
                    "kind": "editorial",
                    "claim_refs": [],
                    "required": True,
                }
            ]
        )
    )

    normalized = result.sections["section-001"]
    assert normalized.claim_refs == []
    assert normalized.evidence_refs == []
    assert normalized.must_cover == ["Abrir com uma pergunta retórica."]


def test_must_cover_cannot_be_supplied_as_an_orphan_side_channel() -> None:
    payload = {
        "sections": [
            {
                "key": "section-001",
                "title": "Seção",
                "purpose": "Propósito",
                "narrative_role": "desenvolvimento",
                "beat_contracts": [
                    {
                        "editorial_goal": "Transição sem novo fato.",
                        "kind": "editorial",
                        "claim_refs": [],
                        "required": False,
                    }
                ],
                "must_cover": ["Instagram, hashtags e intenção da Rockstar"],
                "must_not_repeat": [],
                "transition_target": None,
            }
        ]
    }

    with pytest.raises(ValueError, match="must_cover"):
        PlannedSectionBatchOutput.model_validate(payload)


@pytest.mark.parametrize(
    "status",
    ["reported", "official_observation", "speculation", "inference"],
)
def test_planning_gate_preserves_claim_epistemic_status(status: str) -> None:
    claim = _claim(status=status)
    result = _validate(
        _section(
            beats=[
                {
                    "editorial_goal": "Usar o claim somente dentro do seu escopo.",
                    "kind": "claim_backed",
                    "claim_refs": [claim.id],
                    "required": True,
                }
            ]
        ),
        claims=[claim],
    )

    assert result.issues_by_section == {}
    assert claim.claim_status == status
    assert result.sections["section-001"].claim_refs == [claim.id]


def test_real_regression_rejects_planner_specificity_without_claims() -> None:
    orphan_details = [
        "Explicar imagens verticais para Instagram e TikTok.",
        "Descrever notificações, emojis e hashtags.",
        "Afirmar que redes sociais moldam identidades e alianças.",
        "Explicar a intenção editorial da Rockstar.",
    ]
    result = _validate(
        _section(
            beats=[
                {
                    "editorial_goal": detail,
                    "kind": "claim_backed",
                    "claim_refs": [],
                    "required": True,
                }
                for detail in orphan_details
            ]
        ),
        claims=[_claim()],
    )

    assert result.sections == {}
    issues = result.issues_by_section["section-001"]
    assert sum(issue.code == "orphan_factual_beat" for issue in issues) == 4
