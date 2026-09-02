"""Regression tests for negative assertion and epistemic drift enforcement.

These tests verify the host-side enforcement that blocks when:
A. Negative assertions appear without supporting claims
B. Epistemic mode drifts from canonical claim_status
C. Both issues appear together
D. Multiple negative assertions in same section
E. Epistemic drift for speculation/inference claims
F. Valid prose passes without blockers
G. Backward compatibility with missing fields
H. Bounded assertion types and epistemic modes
I. Complete assessment coverage for all used claims
J. Negative assertion validation: unknown claim_ref, not in actual_claim_refs, support_preserved=false
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.generation import (
    ClaimLanguageAssessment,
    EditorialCriticIssue,
    NegativeWorldStateAssertion,
    SectionEditorialAuditOutput,
)
from app.services.script_generation_jobs import (
    _enforce_negative_assertions_and_epistemic_drift,
)


def _claim(
    claim_id: str = "claim-a",
    *,
    status: str = "reported",
    summary: str = "Uma fonte relata um detalhe.",
    support_scope: str | None = None,
) -> dict:
    return {
        "id": claim_id,
        "summary": summary,
        "claim_status": status,
        "source_trust": "unverified",
        "source_refs": ["source-a"],
        "support_scope": support_scope,
    }


def _audit(
    *,
    issues: list[EditorialCriticIssue] | None = None,
    claim_refs: list[str] | None = None,
    assessments: list[ClaimLanguageAssessment] | None = None,
    negative_assertions: list[NegativeWorldStateAssertion] | None = None,
) -> SectionEditorialAuditOutput:
    return SectionEditorialAuditOutput(
        revision_required=False,
        issues=issues or [],
        actual_claim_refs=claim_refs or [],
        actual_beats_covered=[],
        actual_summary="Test summary.",
        opened_loops=[],
        closed_loops=[],
        claim_language_assessments=assessments or [],
        negative_world_state_assertions=negative_assertions or [],
    )


class TestBoundedAssertionType:
    """Test H: Assertion type must be from bounded vocabulary."""

    def test_valid_assertion_types_accepted(self) -> None:
        """Valid assertion types should be accepted."""
        for assertion_type in [
            "absence_of_confirmation",
            "absence_of_announcement",
            "absence_of_evidence",
            "absence_of_publication",
            "absence_of_showing",
            "unknown_state",
            "speculative_state",
            "other_negative_world_state",
        ]:
            neg = NegativeWorldStateAssertion(
                excerpt="Test assertion",
                assertion_type=assertion_type,
                claim_ref=None,
                support_preserved=None,
            )
            assert neg.assertion_type == assertion_type

    def test_invalid_assertion_type_rejected(self) -> None:
        """Invalid assertion type should be rejected."""
        with pytest.raises(ValidationError):
            NegativeWorldStateAssertion(
                excerpt="Test assertion",
                assertion_type="invalid_type",
                claim_ref=None,
                support_preserved=None,
            )


class TestBoundedEpistemicMode:
    """Test H: Observed epistemic mode must be from bounded vocabulary."""

    def test_valid_epistemic_modes_accepted(self) -> None:
        """Valid epistemic modes should be accepted."""
        for mode in [
            "confirmed",
            "official_observation",
            "reported",
            "strongly_supported",
            "interpretation",
            "inference",
            "rumor",
            "leak",
            "speculation",
            "unknown",
            "author_opinion",
            "gameplay_observation",
        ]:
            assessment = ClaimLanguageAssessment(
                claim_ref="claim-a",
                language_proportional=True,
                attribution_present=True,
                qualification_present=True,
                scope_preserved=True,
                observed_epistemic_mode=mode,
            )
            assert assessment.observed_epistemic_mode == mode

    def test_invalid_epistemic_mode_rejected(self) -> None:
        """Invalid epistemic mode should be rejected."""
        with pytest.raises(ValidationError):
            ClaimLanguageAssessment(
                claim_ref="claim-a",
                language_proportional=True,
                attribution_present=True,
                qualification_present=True,
                scope_preserved=True,
                observed_epistemic_mode="probably_reported",
            )

    def test_arbitrary_string_rejected(self) -> None:
        """Arbitrary string epistemic modes should be rejected."""
        with pytest.raises(ValidationError):
            ClaimLanguageAssessment(
                claim_ref="claim-a",
                language_proportional=True,
                attribution_present=True,
                qualification_present=True,
                scope_preserved=True,
                observed_epistemic_mode="attributed_report",
            )


class TestNegativeAssertionValidation:
    """Test J: Full negative assertion validation."""

    def test_null_ref_is_blocker(self) -> None:
        """A. Negative assertion with claim_ref=None is blocked."""
        audit = _audit(
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem confirmação da Rockstar",
                    assertion_type="absence_of_confirmation",
                    claim_ref=None,
                    support_preserved=None,
                )
            ]
        )
        claims = [_claim()]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert len(result.issues) == 1
        assert result.issues[0].category == "unsupported_negative_assertion"
        assert result.issues[0].severity == "blocking"

    def test_unknown_ref_is_blocker(self) -> None:
        """B. Negative assertion with unknown claim_ref is blocked."""
        audit = _audit(
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem confirmação da Rockstar",
                    assertion_type="absence_of_confirmation",
                    claim_ref="claim-inexistente",
                    support_preserved=True,
                )
            ]
        )
        claims = [_claim()]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert result.issues[0].category == "unsupported_negative_assertion"
        assert "não existe" in result.issues[0].actionable_feedback

    def test_known_but_unrelated_claim_is_blocker(self) -> None:
        """C. Negative assertion with claim not in actual_claim_refs is blocked."""
        audit = _audit(
            claim_refs=["claim-b"],  # Different claim used
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-b",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                )
            ],
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem confirmação de multiplayer",
                    assertion_type="absence_of_confirmation",
                    claim_ref="claim-a",  # This claim exists but not in actual_claim_refs
                    support_preserved=True,
                )
            ],
        )
        claims = [
            _claim(claim_id="claim-a", status="reported"),
            _claim(claim_id="claim-b", status="reported"),
        ]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert any(i.category == "unsupported_negative_assertion" for i in result.issues)

    def test_support_preserved_false_is_blocker(self) -> None:
        """E. Negative assertion with support_preserved=false is blocked."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                )
            ],
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem confirmação de multiplayer",
                    assertion_type="absence_of_confirmation",
                    claim_ref="claim-a",
                    support_preserved=False,  # Claim doesn't support this assertion
                )
            ],
        )
        claims = [_claim(status="reported")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert any(i.category == "unsupported_negative_assertion" for i in result.issues)

    def test_fully_supported_negative_assertion_passes(self) -> None:
        """F. Negative assertion with valid claim_ref and support_preserved=true passes."""
        # Claim with support_scope indicating it represents absence of announcement
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                )
            ],
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Até a data da reportagem, a Rockstar não havia anunciado pré-encomendas.",
                    assertion_type="absence_of_announcement",
                    claim_ref="claim-a",
                    support_preserved=True,
                )
            ],
        )
        claims = [
            _claim(
                status="reported",
                summary="Rockstar não anunciou pré-encomendas.",
                support_scope="Somente ausência de anúncio de pré-encomendas até a data da fonte.",
            )
        ]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert len(result.issues) == 0
        assert result.revision_required is False


class TestCompleteAssessmentCoverage:
    """Test I: Every claim in actual_claim_refs must have exactly one assessment."""

    def test_missing_assessment_is_blocker(self) -> None:
        """H. Missing assessment for a used claim is blocked."""
        audit = _audit(
            claim_refs=["claim-a", "claim-b"],
            assessments=[
                # Only claim-a has assessment, claim-b is missing
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                )
            ],
        )
        claims = [
            _claim(claim_id="claim-a", status="reported"),
            _claim(claim_id="claim-b", status="confirmed"),
        ]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert any("não possui assessment" in i.actionable_feedback for i in result.issues)

    def test_extra_assessment_is_blocker(self) -> None:
        """Assessment for claim not in actual_claim_refs is blocked."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                ),
                # Extra assessment for claim not used
                ClaimLanguageAssessment(
                    claim_ref="claim-b",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="confirmed",
                ),
            ],
        )
        claims = [
            _claim(claim_id="claim-a", status="reported"),
            _claim(claim_id="claim-b", status="confirmed"),
        ]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert any("não está em actual_claim_refs" in i.actionable_feedback for i in result.issues)


class TestEpistemicDrift:
    """Test B: Epistemic mode drift from canonical claim_status is blocked."""

    def test_reported_rendered_as_rumor_is_drift(self) -> None:
        """Regression: claim_status=reported rendered as 'rumor' should block."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="rumor",
                )
            ],
        )
        claims = [_claim(status="reported")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert len(result.issues) == 1
        assert result.issues[0].category == "epistemic_drift"
        assert result.issues[0].severity == "blocking"
        assert "reported" in result.issues[0].actionable_feedback
        assert "rumor" in result.issues[0].actionable_feedback

    def test_reported_rendered_as_reported_passes(self) -> None:
        """Claim with status=reported rendered as 'reported' passes."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                )
            ],
        )
        claims = [_claim(status="reported")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert len(result.issues) == 0

    def test_missing_epistemic_mode_is_blocker(self) -> None:
        """When LLM doesn't detect epistemic mode, block."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode=None,
                )
            ],
        )
        claims = [_claim(status="reported")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert result.issues[0].category == "epistemic_drift"

    def test_confirmed_rendered_as_rumor_is_drift(self) -> None:
        """I. Confirmed claim rendered as rumor is epistemic drift."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=False,
                    qualification_present=False,
                    scope_preserved=True,
                    observed_epistemic_mode="rumor",
                )
            ],
        )
        claims = [_claim(status="confirmed")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert result.issues[0].category == "epistemic_drift"


class TestCombinedIssues:
    """Test C: Both negative assertion and epistemic drift in same section."""

    def test_both_issues_detected(self) -> None:
        """Both negative assertion and epistemic drift should each produce issues."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="rumor",
                )
            ],
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem confirmação da Rockstar",
                    assertion_type="absence_of_confirmation",
                    claim_ref=None,
                    support_preserved=None,
                )
            ],
        )
        claims = [_claim(status="reported")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert len(result.issues) == 2
        categories = {issue.category for issue in result.issues}
        assert "unsupported_negative_assertion" in categories
        assert "epistemic_drift" in categories


class TestMultipleNegativeAssertions:
    """Test D: Multiple negative assertions in same section."""

    def test_multiple_negative_assertions_without_claims(self) -> None:
        """Each negative assertion without claim produces a blocker."""
        audit = _audit(
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem confirmação da Rockstar",
                    assertion_type="absence_of_confirmation",
                    claim_ref=None,
                    support_preserved=None,
                ),
                NegativeWorldStateAssertion(
                    excerpt="Não há evidência de multiplayer",
                    assertion_type="absence_of_evidence",
                    claim_ref=None,
                    support_preserved=None,
                ),
            ]
        )
        claims = [_claim()]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert len(result.issues) == 2
        assert all(i.category == "unsupported_negative_assertion" for i in result.issues)


class TestSpeculationInferenceDrift:
    """Test E: Epistemic drift for speculation/inference claims."""

    def test_speculation_rendered_as_confirmed_is_drift(self) -> None:
        """Speculation claim rendered as confirmed is epistemic drift."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=False,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="confirmed",
                )
            ],
        )
        claims = [_claim(status="speculation")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert result.issues[0].category == "epistemic_drift"

    def test_inference_rendered_as_reported_is_drift(self) -> None:
        """Inference claim rendered as reported is epistemic drift."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=False,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                )
            ],
        )
        claims = [_claim(status="inference")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.issues[0].category == "epistemic_drift"


class TestValidProsePasses:
    """Test F: Valid prose passes without blockers."""

    def test_all_constraints_satisfied(self) -> None:
        """Prose that satisfies all constraints passes."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                )
            ],
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem anúncio oficial",
                    assertion_type="absence_of_announcement",
                    claim_ref="claim-a",
                    support_preserved=True,
                )
            ],
        )
        claims = [_claim(status="reported", support_scope="Ausência de anúncio oficial")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert len(result.issues) == 0
        assert result.revision_required is False


class TestBackwardCompatibility:
    """Test G: Backward compatibility with missing fields."""

    def test_missing_negative_assertions_field(self) -> None:
        """Audit without negative_world_state_assertions field should not crash."""
        audit = SectionEditorialAuditOutput(
            revision_required=False,
            issues=[],
            actual_claim_refs=["claim-a"],
            actual_beats_covered=[],
            actual_summary="Test.",
            opened_loops=[],
            closed_loops=[],
            claim_language_assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="reported",
                )
            ],
            # negative_world_state_assertions not provided - uses default []
        )
        claims = [_claim(status="reported")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert len(result.issues) == 0


class TestRealRegressionCases:
    """Tests based on actual false negatives from tiny run."""

    def test_gta6_sem_confirmacao_case(self) -> None:
        """Regression: 'Sem nenhuma confirmação direta da Rockstar' case."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="rumor",  # Drift from reported
                )
            ],
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem nenhuma confirmação direta da Rockstar até este ponto",
                    assertion_type="absence_of_confirmation",
                    claim_ref=None,  # No supporting claim
                    support_preserved=None,
                )
            ],
        )
        claims = [_claim(status="reported")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        # Should catch BOTH issues
        assert result.revision_required is True
        assert len(result.issues) == 2

        categories = {issue.category for issue in result.issues}
        assert "unsupported_negative_assertion" in categories
        assert "epistemic_drift" in categories

    def test_claim_rendered_as_campo_do_rumor(self) -> None:
        """Regression: 'campo do rumor' phrasing for reported claims."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=True,
                    qualification_present=True,
                    scope_preserved=True,
                    observed_epistemic_mode="rumor",
                )
            ],
        )
        claims = [_claim(status="reported")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.issues[0].category == "epistemic_drift"
        assert "reported" in result.issues[0].actionable_feedback.lower()


class TestAuditOutputContract:
    """Test that _section_audit_output_contract includes new fields."""

    def test_contract_mentions_negative_world_state_assertions(self) -> None:
        """Contract must explicitly mention negative_world_state_assertions."""
        from app.services.script_generation_jobs import _section_audit_output_contract

        contract = _section_audit_output_contract()
        assert "negative_world_state_assertions" in contract

    def test_contract_mentions_observed_epistemic_mode(self) -> None:
        """Contract must explicitly mention observed_epistemic_mode."""
        from app.services.script_generation_jobs import _section_audit_output_contract

        contract = _section_audit_output_contract()
        assert "observed_epistemic_mode" in contract

    def test_contract_mentions_support_preserved(self) -> None:
        """Contract must mention support_preserved."""
        from app.services.script_generation_jobs import _section_audit_output_contract

        contract = _section_audit_output_contract()
        assert "support_preserved" in contract

    def test_contract_mentions_all_assessments_required(self) -> None:
        """Contract must indicate all claims need assessment."""
        from app.services.script_generation_jobs import _section_audit_output_contract

        contract = _section_audit_output_contract()
        assert "EXATLY ONE assessment for EVERY claim" in contract or "exactly one assessment" in contract.lower()
