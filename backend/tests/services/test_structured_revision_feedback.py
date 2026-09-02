"""Unit tests for structured targeted revision feedback."""

from __future__ import annotations

import pytest

from app.schemas.generation import EditorialCriticIssue, SectionEditorialAuditOutput
from app.services.script_generation_jobs import (
    StructuredRevisionIssue,
    TargetedRevisionFeedback,
    _targeted_section_feedback,
)


def _issue(
    *,
    category: str = "uncertainty_lost",
    severity: str = "revision_required",
    feedback: str = "Restore attribution.",
    claim_ref: str | None = None,
    excerpt: str | None = None,
) -> EditorialCriticIssue:
    return EditorialCriticIssue(
        category=category,
        severity=severity,
        actionable_feedback=feedback,
        claim_ref=claim_ref,
        excerpt=excerpt,
    )


def _audit(issues: list[EditorialCriticIssue]) -> SectionEditorialAuditOutput:
    return SectionEditorialAuditOutput(
        revision_required=True,
        issues=issues,
        actual_claim_refs=[],
        actual_beats_covered=[],
        actual_summary="Test summary.",
        opened_loops=[],
        closed_loops=[],
        claim_language_assessments=[],
    )


class TestTargetedRevisionFeedback:
    """Tests for TargetedRevisionFeedback dataclass."""

    def test_to_prompt_text_with_word_feedback(self) -> None:
        feedback = TargetedRevisionFeedback(
            word_feedback="Word contract: actual=100 target=150 status=under.",
            issues=[],
        )
        result = feedback.to_prompt_text()

        assert "TARGETED SECTION REVISION" in result
        assert "Word contract:" in result

    def test_to_prompt_text_with_issues(self) -> None:
        feedback = TargetedRevisionFeedback(
            word_feedback=None,
            issues=[
                StructuredRevisionIssue(
                    category="uncertainty_lost",
                    severity="revision_required",
                    actionable_feedback="Restore attribution.",
                    claim_ref="claim-a",
                    excerpt="O jogo terá multiplayer.",
                )
            ],
        )
        result = feedback.to_prompt_text()

        assert "uncertainty_lost: Restore attribution." in result
        assert "Trecho: 'O jogo terá multiplayer.'" in result

    def test_to_prompt_text_without_excerpt(self) -> None:
        feedback = TargetedRevisionFeedback(
            word_feedback=None,
            issues=[
                StructuredRevisionIssue(
                    category="unsupported_claim",
                    severity="blocking",
                    actionable_feedback="Remove claim.",
                    claim_ref=None,
                    excerpt=None,
                )
            ],
        )
        result = feedback.to_prompt_text()

        assert "unsupported_claim: Remove claim." in result
        assert "Trecho:" not in result


class TestTargetedSectionFeedback:
    """Tests for _targeted_section_feedback function."""

    def test_claim_ref_preserved(self) -> None:
        """Issue with claim_ref appears in structured output."""
        audit = _audit([_issue(claim_ref="claim-a")])
        validation = {"revision_required": False}

        result = _targeted_section_feedback(validation, audit)

        assert len(result.issues) == 1
        assert result.issues[0].claim_ref == "claim-a"

    def test_excerpt_preserved(self) -> None:
        """Issue with excerpt appears verbatim in structured output."""
        audit = _audit([_issue(excerpt="trecho problemático exato")])
        validation = {"revision_required": False}

        result = _targeted_section_feedback(validation, audit)

        assert result.issues[0].excerpt == "trecho problemático exato"

    def test_null_claim_ref_preserved(self) -> None:
        """claim_ref=None remains None, not stripped."""
        audit = _audit([_issue(claim_ref=None)])
        validation = {"revision_required": False}

        result = _targeted_section_feedback(validation, audit)

        assert result.issues[0].claim_ref is None

    def test_null_excerpt_preserved(self) -> None:
        """excerpt=None remains None, not stripped."""
        audit = _audit([_issue(excerpt=None)])
        validation = {"revision_required": False}

        result = _targeted_section_feedback(validation, audit)

        assert result.issues[0].excerpt is None

    def test_multiple_issues_all_preserved(self) -> None:
        """All revision issues are preserved in structured output."""
        audit = _audit(
            [
                _issue(
                    category="uncertainty_lost",
                    claim_ref="claim-a",
                    excerpt="Texto A",
                ),
                _issue(
                    category="unsupported_specificity",
                    claim_ref="claim-b",
                    excerpt="Texto B",
                ),
                _issue(
                    category="unsupported_claim",
                    claim_ref=None,
                    excerpt="Texto C",
                ),
            ]
        )
        validation = {"revision_required": False}

        result = _targeted_section_feedback(validation, audit)

        assert len(result.issues) == 3
        assert result.issues[0].claim_ref == "claim-a"
        assert result.issues[1].claim_ref == "claim-b"
        assert result.issues[2].claim_ref is None

    def test_word_validation_included_in_feedback(self) -> None:
        """Word validation feedback is included."""
        audit = _audit([])
        validation = {
            "revision_required": True,
            "actual_words": 50,
            "target_words": 100,
            "status": "under",
        }

        result = _targeted_section_feedback(validation, audit)

        assert result.word_feedback is not None
        assert "actual=50" in result.word_feedback
        assert "target=100" in result.word_feedback

    def test_warning_issues_not_included(self) -> None:
        """Warning severity issues are not included in revision feedback."""
        audit = _audit(
            [
                _issue(severity="warning", claim_ref="claim-a"),
                _issue(severity="revision_required", claim_ref="claim-b"),
            ]
        )
        validation = {"revision_required": False}

        result = _targeted_section_feedback(validation, audit)

        # Only revision_required issues should be included
        assert len(result.issues) == 1
        assert result.issues[0].claim_ref == "claim-b"

    def test_factual_blocker_included(self) -> None:
        """Factual blocker issues are included regardless of severity."""
        # Note: _issue_is_factual_blocker checks for specific categories
        audit = _audit(
            [
                _issue(
                    category="unsupported_claim",
                    severity="warning",
                    claim_ref="claim-a",
                ),
            ]
        )
        validation = {"revision_required": False}

        result = _targeted_section_feedback(validation, audit)

        # unsupported_claim should be included even as warning
        # (factual blockers are included)
        assert len(result.issues) == 1

    def test_no_audit_returns_empty_issues(self) -> None:
        """When audit is None, returns empty issues list."""
        validation = {"revision_required": False}

        result = _targeted_section_feedback(validation, None)

        assert result.issues == []
        assert result.word_feedback is None


class TestStructuredRevisionIssue:
    """Tests for StructuredRevisionIssue dataclass."""

    def test_frozen_dataclass(self) -> None:
        """StructuredRevisionIssue is immutable."""
        issue = StructuredRevisionIssue(
            category="test",
            severity="revision_required",
            actionable_feedback="Fix it.",
            claim_ref="claim-a",
            excerpt="text",
        )

        with pytest.raises(AttributeError):
            issue.category = "modified"  # type: ignore

    def test_all_fields_preserved(self) -> None:
        """All fields are preserved correctly."""
        issue = StructuredRevisionIssue(
            category="uncertainty_lost",
            severity="blocking",
            actionable_feedback="Restore attribution.",
            claim_ref="claim-123",
            excerpt="Problematic text.",
        )

        assert issue.category == "uncertainty_lost"
        assert issue.severity == "blocking"
        assert issue.actionable_feedback == "Restore attribution."
        assert issue.claim_ref == "claim-123"
        assert issue.excerpt == "Problematic text."
