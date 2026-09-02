"""Regression tests for negative assertion and epistemic drift enforcement.

These tests verify the host-side enforcement that blocks when:
A. Negative assertions appear without supporting claims
B. Epistemic mode drifts from canonical claim_status
C. Both issues appear together
D. Multiple negative assertions in same section
E. Epistemic drift for speculation/inference claims
F. Valid prose passes without blockers
G. Backward compatibility with missing fields
"""

from __future__ import annotations

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
) -> dict:
    return {
        "id": claim_id,
        "summary": summary,
        "claim_status": status,
        "source_trust": "unverified",
        "source_refs": ["source-a"],
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


class TestUnsupportedNegativeAssertion:
    """Test A: Negative assertion without claim provenance is blocked."""

    def test_negative_assertion_without_claim_is_blocker(self) -> None:
        """Regression: 'Sem confirmação da Rockstar' without claim should block."""
        audit = _audit(
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem nenhuma confirmação direta da Rockstar",
                    assertion_type="absence_of_confirmation",
                    claim_ref=None,
                )
            ]
        )
        claims = [_claim()]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert result.revision_required is True
        assert len(result.issues) == 1
        assert result.issues[0].category == "unsupported_negative_assertion"
        assert result.issues[0].severity == "blocking"

    def test_negative_assertion_with_claim_is_allowed(self) -> None:
        """Negative assertion WITH supporting claim passes."""
        audit = _audit(
            negative_assertions=[
                NegativeWorldStateAssertion(
                    excerpt="Sem confirmação oficial",
                    assertion_type="absence_of_confirmation",
                    claim_ref="claim-a",
                )
            ]
        )
        claims = [_claim()]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        assert len(result.issues) == 0


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

    def test_missing_epistemic_mode_for_reported_is_blocker(self) -> None:
        """When LLM doesn't detect epistemic mode for reported claim, block."""
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
                ),
                NegativeWorldStateAssertion(
                    excerpt="Não há evidência de multiplayer",
                    assertion_type="absence_of_evidence",
                    claim_ref=None,
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
                    assertion_type="absence_of_confirmation",
                    claim_ref="claim-a",
                )
            ],
        )
        claims = [_claim(status="reported")]

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

    def test_missing_observed_epistemic_mode_for_confirmed(self) -> None:
        """Confirmed claims don't require epistemic mode detection."""
        audit = _audit(
            claim_refs=["claim-a"],
            assessments=[
                ClaimLanguageAssessment(
                    claim_ref="claim-a",
                    language_proportional=True,
                    attribution_present=False,
                    qualification_present=False,
                    scope_preserved=True,
                    observed_epistemic_mode=None,
                )
            ],
        )
        claims = [_claim(status="confirmed")]

        result = _enforce_negative_assertions_and_epistemic_drift(audit, claims)

        # Confirmed claims don't require epistemic mode detection
        # (only reported claims require it)
        assert len(result.issues) == 0


class TestRealRegressionCases:
    """Tests based on actual false negatives from tiny run."""

    def test_gta6_sem_confirmacao_case(self) -> None:
        """Regression: 'Sem nenhuma confirmação direta da Rockstar' case."""
        # This was the actual prose that passed audit incorrectly
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
