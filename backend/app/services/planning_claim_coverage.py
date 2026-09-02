"""Host-owned claim coverage validation for Editorial V3 section plans."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.generation import (
    PlannedClaimOutput,
    PlannedSectionOutput,
    PlannedSectionV2Output,
)

EXPLICIT_CLAIM_COVERAGE_VERSION = "explicit_claim_coverage_v1"


@dataclass(frozen=True)
class PlanningCoverageIssue:
    section_key: str
    code: str
    message: str
    beat_index: int | None = None
    editorial_goal: str | None = None

    def as_dict(self) -> dict[str, object | None]:
        return {
            "section_key": self.section_key,
            "code": self.code,
            "message": self.message,
            "beat_index": self.beat_index,
            "editorial_goal": self.editorial_goal,
        }


@dataclass(frozen=True)
class PlanningCoverageResult:
    sections: dict[str, PlannedSectionOutput]
    issues_by_section: dict[str, list[PlanningCoverageIssue]]
    total_beats: int
    claim_backed_beats: int
    editorial_beats: int

    @property
    def rejected_beats(self) -> int:
        return len(
            {
                (issue.section_key, issue.beat_index)
                for issues in self.issues_by_section.values()
                for issue in issues
                if issue.beat_index is not None
            }
        )

    @property
    def invalid_section_keys(self) -> list[str]:
        return list(self.issues_by_section)


def validate_and_normalize_section_coverage(
    sections: list[PlannedSectionV2Output],
    *,
    claim_ledger: list[PlannedClaimOutput],
    known_source_ids: set[str],
    grounding_required: bool,
    planning_version: str,
) -> PlanningCoverageResult:
    """Validate beat provenance and derive every section-level grounding field."""

    known_claims = {claim.id: claim for claim in claim_ledger}
    normalized: dict[str, PlannedSectionOutput] = {}
    issues_by_section: dict[str, list[PlanningCoverageIssue]] = {}
    total_beats = 0
    claim_backed_beats = 0
    editorial_beats = 0

    for section in sections:
        issues: list[PlanningCoverageIssue] = []
        derived_claim_refs: list[str] = []
        total_beats += len(section.beat_contracts)
        for index, beat in enumerate(section.beat_contracts):
            if beat.kind == "claim_backed":
                claim_backed_beats += 1
                if not beat.claim_refs:
                    issues.append(
                        PlanningCoverageIssue(
                            section_key=section.key,
                            code="orphan_factual_beat",
                            message="claim-backed beat requires at least one approved claim",
                            beat_index=index,
                            editorial_goal=beat.editorial_goal,
                        )
                    )
                unknown = [
                    claim_id
                    for claim_id in beat.claim_refs
                    if claim_id not in known_claims
                ]
                if unknown:
                    issues.append(
                        PlanningCoverageIssue(
                            section_key=section.key,
                            code="unknown_claim_ref",
                            message=f"unknown claim refs: {sorted(set(unknown))}",
                            beat_index=index,
                            editorial_goal=beat.editorial_goal,
                        )
                    )
                for claim_id in beat.claim_refs:
                    if claim_id in known_claims and claim_id not in derived_claim_refs:
                        derived_claim_refs.append(claim_id)
            else:
                editorial_beats += 1
                if beat.claim_refs:
                    issues.append(
                        PlanningCoverageIssue(
                            section_key=section.key,
                            code="editorial_beat_has_claim_refs",
                            message=(
                                "editorial beats are rhetorical structure only; use "
                                "claim_backed for claim obligations"
                            ),
                            beat_index=index,
                            editorial_goal=beat.editorial_goal,
                        )
                    )

        if grounding_required and known_claims and not derived_claim_refs:
            issues.append(
                PlanningCoverageIssue(
                    section_key=section.key,
                    code="grounded_section_without_claims",
                    message="grounded section has no approved claim-backed beat",
                )
            )

        derived_evidence_refs: list[str] = []
        for claim_id in derived_claim_refs:
            for source_ref in known_claims[claim_id].source_refs:
                if source_ref not in known_source_ids:
                    issues.append(
                        PlanningCoverageIssue(
                            section_key=section.key,
                            code="unknown_evidence_ref",
                            message=(
                                f"claim {claim_id} references unknown evidence "
                                f"source {source_ref}"
                            ),
                        )
                    )
                elif source_ref not in derived_evidence_refs:
                    derived_evidence_refs.append(source_ref)

        if issues:
            issues_by_section[section.key] = issues
            continue

        beat_labels = [beat.editorial_goal for beat in section.beat_contracts]
        normalized[section.key] = PlannedSectionOutput(
            key=section.key,
            title=section.title,
            purpose=section.purpose,
            narrative_role=section.narrative_role,
            beats=beat_labels,
            evidence_refs=derived_evidence_refs,
            claim_refs=derived_claim_refs,
            must_cover=[
                beat.editorial_goal for beat in section.beat_contracts if beat.required
            ],
            must_not_repeat=section.must_not_repeat,
            transition_target=section.transition_target,
            beat_contracts=section.beat_contracts,
            planning_version=planning_version,
        )

    return PlanningCoverageResult(
        sections=normalized,
        issues_by_section=issues_by_section,
        total_beats=total_beats,
        claim_backed_beats=claim_backed_beats,
        editorial_beats=editorial_beats,
    )
