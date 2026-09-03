"""Deterministic host-owned context for explicit script revision runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Set
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from app.schemas.roteiro import RoteiroEstrutura, script_content_identity
from app.services.duration_contract import revision_duration_diagnostics

REVISION_BRIEF_VERSION = "script_revision_brief_v1"


@dataclass(frozen=True)
class RevisionBrief:
    version: str
    identity: str
    parent: dict[str, Any]
    human_feedback: str | None
    editorial: dict[str, Any]
    duration: dict[str, Any]
    sections: tuple[dict[str, Any], ...]
    preserve: tuple[dict[str, Any], ...]
    revision_priorities: tuple[dict[str, Any], ...]
    evidence_reuse: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_revision_brief(
    *,
    parent_roteiro_id: UUID,
    parent_version: int | None,
    parent_revision_kind: str | None,
    structure: RoteiroEstrutura,
    human_feedback: str | None,
    evidence_provenance: dict[str, Any],
    factual_issue_categories: Set[str],
) -> RevisionBrief:
    """Build a durable revision brief exclusively from persisted parent data."""

    normalized_feedback = (
        human_feedback.strip() if human_feedback and human_feedback.strip() else None
    )
    review = structure.editorial_review or {}
    critic = structure.global_critic or {}
    global_issues = _issue_dicts(
        review.get("global_issues") or critic.get("issues") or []
    )
    duration = revision_duration_diagnostics(structure.duration_contract)
    duration_sections = {
        item["section_key"]: item for item in duration.get("sections") or []
    }
    persisted_section_audits = structure.section_audits or {}
    review_section_issues = review.get("section_issues") or {}

    parent_blocks: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    preserve: list[dict[str, Any]] = []
    for index, block in enumerate(structure.blocos):
        section_key = f"section-{index + 1:03d}"
        audit = persisted_section_audits.get(section_key)
        audit_value = audit if isinstance(audit, dict) else {}
        issues = _issue_dicts(
            audit_value.get("issues") or review_section_issues.get(section_key) or []
        )
        review_state = _section_review_state(
            audit,
            issues,
            factual_issue_categories=factual_issue_categories,
        )
        parent_blocks.append(
            {
                "section_key": section_key,
                "type": block.tipo,
                "purpose": block.purpose,
                "current_content": block.conteudo,
            }
        )
        section_value = {
            "section_key": section_key,
            "type": block.tipo,
            "purpose": block.purpose,
            "review_state": review_state,
            "audit_revision_required": bool(audit_value.get("revision_required")),
            "audit_summary": audit_value.get("actual_summary"),
            "audit_issues": issues,
            "opened_loops": list(audit_value.get("opened_loops") or []),
            "closed_loops": list(audit_value.get("closed_loops") or []),
            "duration": duration_sections.get(section_key),
        }
        sections.append(section_value)
        if review_state == "clean":
            preserve.append(
                {
                    "section_key": section_key,
                    "reason": "No persisted section issue requires rewriting this material.",
                }
            )

    editorial = {
        "audit_status": review.get("audit_status") or structure.audit_status,
        "editorial_status": review.get("editorial_status"),
        "factuality_status": review.get("factuality_status"),
        "global_summary": review.get("global_summary") or critic.get("summary"),
        "global_issues": global_issues,
    }
    if editorial["factuality_status"] == "pass":
        preserve.insert(
            0,
            {
                "scope": "global",
                "reason": "Preserve the parent script's passing factual discipline and evidence boundaries.",
            },
        )

    priorities = _revision_priorities(
        human_feedback=normalized_feedback,
        global_issues=global_issues,
        sections=sections,
        duration=duration,
        factual_issue_categories=factual_issue_categories,
    )
    parent = {
        "roteiro_id": str(parent_roteiro_id),
        "version": parent_version,
        "revision_kind": parent_revision_kind,
        "generation_run_id": structure.generation_run_id,
        "source_generation_run_id": structure.source_generation_run_id,
        "strategy_identity": (structure.prompt_trace or {}).get("strategy_identity"),
        "content_identity": script_content_identity(structure),
        "title": structure.titulo,
        "blocks": parent_blocks,
    }
    evidence_reuse = {
        "available": bool(evidence_provenance),
        "generation_run_id": evidence_provenance.get("generation_run_id"),
        "claim_ledger_version": evidence_provenance.get("claim_ledger_version"),
        "claim_count": len(evidence_provenance.get("claim_ledger") or []),
        "source_count": len(evidence_provenance.get("sources") or []),
    }
    payload = {
        "version": REVISION_BRIEF_VERSION,
        "parent": parent,
        "human_feedback": normalized_feedback,
        "editorial": editorial,
        "duration": duration,
        "sections": sections,
        "preserve": preserve,
        "revision_priorities": priorities,
        "evidence_reuse": evidence_reuse,
    }
    identity = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return RevisionBrief(
        version=REVISION_BRIEF_VERSION,
        identity=identity,
        parent=parent,
        human_feedback=normalized_feedback,
        editorial=editorial,
        duration=duration,
        sections=tuple(sections),
        preserve=tuple(preserve),
        revision_priorities=tuple(priorities),
        evidence_reuse=evidence_reuse,
    )


def scoped_revision_context(
    brief: dict[str, Any] | None,
    *,
    section_keys: set[str] | None = None,
) -> dict[str, Any] | None:
    """Return a compact prompt projection without changing durable provenance.

    The persisted brief deliberately keeps raw reviews plus ranked priorities. Prompts
    need each fact once: human feedback comes from its dedicated field, duration from
    its deterministic contract, and editorial issues from the ranked priorities.
    """

    if not brief:
        return None
    parent = dict(brief.get("parent") or {})
    if section_keys is not None:
        parent["blocks"] = [
            item
            for item in parent.get("blocks") or []
            if item.get("section_key") in section_keys
        ]
    duration = dict(brief.get("duration") or {})
    if section_keys is not None:
        duration["sections"] = [
            item
            for item in duration.get("sections") or []
            if item.get("section_key") in section_keys
        ]
    sections = []
    for raw_section in brief.get("sections") or []:
        if (
            section_keys is not None
            and raw_section.get("section_key") not in section_keys
        ):
            continue
        # Exact issues and duration are already represented authoritatively below.
        sections.append(
            {
                key: value
                for key, value in raw_section.items()
                if key not in {"audit_issues", "duration"}
            }
        )
    priorities = _prompt_revision_priorities(
        list(brief.get("revision_priorities") or []), section_keys=section_keys
    )
    preserve = [
        item
        for item in brief.get("preserve") or []
        if section_keys is None
        or not item.get("section_key")
        or item.get("section_key") in section_keys
    ]
    editorial = {
        key: value
        for key, value in dict(brief.get("editorial") or {}).items()
        if key != "global_issues"
    }
    return {
        "version": brief.get("version"),
        "identity": brief.get("identity"),
        "scope": sorted(section_keys) if section_keys is not None else "global",
        "parent": parent,
        "human_feedback": brief.get("human_feedback"),
        "editorial": editorial,
        "duration": duration,
        "sections": sections,
        "revision_priorities": priorities,
        "preserve": preserve,
        "evidence_reuse": brief.get("evidence_reuse") or {},
    }


def _prompt_revision_priorities(
    priorities: list[dict[str, Any]], *, section_keys: set[str] | None
) -> list[dict[str, Any]]:
    """Keep diagnostic priorities once in prompt context.

    Human feedback, duration and generic style already have authoritative prompt
    surfaces. Persisted priority entries remain untouched for later inspection.
    """

    excluded_sources = {"human_feedback", "duration_contract", "revision_semantics"}
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in priorities:
        if item.get("source") in excluded_sources:
            continue
        if (
            section_keys is not None
            and item.get("section_key")
            and item.get("section_key") not in section_keys
        ):
            continue
        signature = (
            item.get("section_key"),
            item.get("category"),
            item.get("action"),
            item.get("excerpt"),
            item.get("claim_ref"),
        )
        if signature in seen:
            continue
        seen.add(signature)
        result.append(item)
    return result


def _revision_priorities(
    *,
    human_feedback: str | None,
    global_issues: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    duration: dict[str, Any],
    factual_issue_categories: Set[str],
) -> list[dict[str, Any]]:
    issue_entries: list[tuple[str, dict[str, Any]]] = [
        ("global_critic", issue) for issue in global_issues
    ]
    issue_entries.extend(
        ("section_audit", {**issue, "section_key": section["section_key"]})
        for section in sections
        for issue in section["audit_issues"]
    )
    seen: set[tuple[Any, ...]] = set()
    factual: list[dict[str, Any]] = []
    editorial: list[dict[str, Any]] = []
    for source, issue in issue_entries:
        entry = {
            "rank": 1 if issue.get("category") in factual_issue_categories else 3,
            "source": source,
            "section_key": issue.get("section_key"),
            "category": issue.get("category") or "editorial",
            "severity": issue.get("severity"),
            "action": issue.get("actionable_feedback"),
            "excerpt": issue.get("excerpt"),
            "claim_ref": issue.get("claim_ref"),
            "diagnostic_only": True,
        }
        signature = (
            entry["source"],
            entry["section_key"],
            entry["category"],
            entry["action"],
            entry["excerpt"],
        )
        if signature in seen:
            continue
        seen.add(signature)
        (factual if entry["rank"] == 1 else editorial).append(entry)

    human = (
        [
            {
                "rank": 2,
                "source": "human_feedback",
                "section_key": None,
                "category": "human_editorial_direction",
                "action": human_feedback,
                "diagnostic_only": True,
            }
        ]
        if human_feedback
        else []
    )
    duration_priorities: list[dict[str, Any]] = []
    if duration.get("revision_required"):
        duration_priorities.append(
            {
                "rank": 4,
                "source": "duration_contract",
                "section_key": None,
                "category": "duration",
                "action": "Expand or compact with supported substance toward the measured target.",
                "target_words": duration.get("target_words"),
                "actual_words": duration.get("actual_words"),
                "word_deficit": duration.get("word_deficit"),
                "word_surplus": duration.get("word_surplus"),
                "status": duration.get("status"),
                "diagnostic_only": True,
            }
        )
    for section in duration.get("sections") or []:
        if section.get("status") in {"excellent", "acceptable", "estimate_only"}:
            continue
        duration_priorities.append(
            {
                "rank": 4,
                "source": "duration_contract",
                "section_key": section.get("section_key"),
                "category": "section_duration",
                "action": "Repair this section's measured word deficit or surplus without filler.",
                "target_words": section.get("target_words"),
                "actual_words": section.get("actual_words"),
                "word_deficit": section.get("word_deficit"),
                "word_surplus": section.get("word_surplus"),
                "status": section.get("status"),
                "diagnostic_only": True,
            }
        )
    generic = [
        {
            "rank": 5,
            "source": "revision_semantics",
            "section_key": None,
            "category": "spoken_editorial_quality",
            "action": "Preserve successful parent material; improve concreteness, progression, natural spoken PT-BR and payoff only where needed.",
            "diagnostic_only": True,
        }
    ]
    return [*factual, *human, *editorial, *duration_priorities, *generic]


def _issue_dicts(values: list[Any]) -> list[dict[str, Any]]:
    return [dict(value) for value in values if isinstance(value, dict)]


def _section_review_state(
    raw_audit: Any,
    issues: list[dict[str, Any]],
    *,
    factual_issue_categories: Set[str],
) -> str:
    if not isinstance(raw_audit, dict):
        return "audit_unavailable"
    if any(
        issue.get("category") in factual_issue_categories
        and issue.get("severity") in {"revision_required", "blocking"}
        for issue in issues
    ):
        return "high_factual_risk"
    if raw_audit.get("revision_required") or issues:
        return "needs_review"
    return "clean"
