"""Versioned, provider-neutral source and claim contracts for Editorial V3."""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlparse

from app.schemas.generation import PlannedClaimOutput

EVIDENCE_DOSSIER_VERSION = "evidence_dossier_v3"
CLAIM_LEDGER_VERSION = "canonical_claim_ledger_v1"


class SourceTrustTier(StrEnum):
    PRIMARY_OFFICIAL = "primary_official"
    RELIABLE_SECONDARY = "reliable_secondary"
    COMMUNITY = "community"
    UNVERIFIED = "unverified"
    HUMAN_AUTHOR = "human_author"
    GAMEPLAY_EVIDENCE = "gameplay_evidence"


class ClaimStatus(StrEnum):
    CONFIRMED = "confirmed"
    OFFICIAL_OBSERVATION = "official_observation"
    REPORTED = "reported"
    STRONGLY_SUPPORTED = "strongly_supported"
    INTERPRETATION = "interpretation"
    INFERENCE = "inference"
    RUMOR = "rumor"
    LEAK = "leak"
    SPECULATION = "speculation"
    UNKNOWN = "unknown"
    AUTHOR_OPINION = "author_opinion"
    GAMEPLAY_OBSERVATION = "gameplay_observation"


_CLAIM_STATUS_CONSERVATIVE_ORDER = (
    ClaimStatus.UNKNOWN,
    ClaimStatus.SPECULATION,
    ClaimStatus.RUMOR,
    ClaimStatus.LEAK,
    ClaimStatus.INFERENCE,
    ClaimStatus.INTERPRETATION,
    ClaimStatus.AUTHOR_OPINION,
    ClaimStatus.OFFICIAL_OBSERVATION,
    ClaimStatus.GAMEPLAY_OBSERVATION,
    ClaimStatus.REPORTED,
    ClaimStatus.STRONGLY_SUPPORTED,
    ClaimStatus.CONFIRMED,
)


class SourcePolicyLike(Protocol):
    @property
    def primary_domains(self) -> tuple[str, ...]: ...

    @property
    def primary_sources(self) -> tuple[Any, ...]: ...

    @property
    def reliable_domains(self) -> tuple[str, ...]: ...

    @property
    def reliable_sources(self) -> tuple[Any, ...]: ...

    @property
    def community_domains(self) -> tuple[str, ...]: ...

    @property
    def unknown_default(self) -> str: ...


_LEGACY_TIER_MAP: dict[str, tuple[SourceTrustTier, ClaimStatus]] = {
    "official_confirmed": (
        SourceTrustTier.PRIMARY_OFFICIAL,
        ClaimStatus.CONFIRMED,
    ),
    "official_observation": (
        SourceTrustTier.PRIMARY_OFFICIAL,
        ClaimStatus.OFFICIAL_OBSERVATION,
    ),
    "reliable_secondary": (
        SourceTrustTier.RELIABLE_SECONDARY,
        ClaimStatus.REPORTED,
    ),
    "leak_authenticated": (
        SourceTrustTier.RELIABLE_SECONDARY,
        ClaimStatus.LEAK,
    ),
    "inference": (SourceTrustTier.UNVERIFIED, ClaimStatus.INFERENCE),
    "speculation": (SourceTrustTier.UNVERIFIED, ClaimStatus.SPECULATION),
    "unverified": (SourceTrustTier.UNVERIFIED, ClaimStatus.UNKNOWN),
    "author_opinion": (SourceTrustTier.HUMAN_AUTHOR, ClaimStatus.AUTHOR_OPINION),
    "gameplay_note": (
        SourceTrustTier.GAMEPLAY_EVIDENCE,
        ClaimStatus.GAMEPLAY_OBSERVATION,
    ),
}


def normalize_domain(url: str) -> str:
    hostname = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    return hostname.rstrip(".")


def _domain_matches(domain: str, configured: tuple[str, ...]) -> bool:
    return any(
        domain == item.casefold().removeprefix("www.")
        or domain.endswith("." + item.casefold().removeprefix("www."))
        for item in configured
    )


def classify_source_trust(
    *,
    url: str,
    source_type: str,
    policy: SourcePolicyLike,
    source_account: str | None = None,
) -> SourceTrustTier:
    if source_type in {"human_gameplay_notes", "gameplay_notes"}:
        return SourceTrustTier.GAMEPLAY_EVIDENCE
    if source_type in {"operator_input", "author_briefing"}:
        return SourceTrustTier.HUMAN_AUTHOR
    domain = normalize_domain(url)
    parsed = urlparse(url)
    for rule in getattr(policy, "primary_sources", ()):
        if _source_rule_matches(
            domain=domain,
            path=parsed.path,
            account=source_account,
            rule=rule,
        ):
            return SourceTrustTier.PRIMARY_OFFICIAL
    if _domain_matches(domain, policy.primary_domains):
        return SourceTrustTier.PRIMARY_OFFICIAL
    for rule in getattr(policy, "reliable_sources", ()):
        if _source_rule_matches(
            domain=domain,
            path=parsed.path,
            account=source_account,
            rule=rule,
        ):
            return SourceTrustTier.RELIABLE_SECONDARY
    if _domain_matches(domain, policy.reliable_domains):
        return SourceTrustTier.RELIABLE_SECONDARY
    if _domain_matches(domain, policy.community_domains):
        return SourceTrustTier.COMMUNITY
    try:
        return SourceTrustTier(policy.unknown_default)
    except ValueError:
        return SourceTrustTier.UNVERIFIED


def _source_rule_matches(
    *, domain: str, path: str, account: str | None, rule: Any
) -> bool:
    host = str(getattr(rule, "host", "")).casefold().removeprefix("www.")
    if domain != host and not domain.endswith("." + host):
        return False
    path_prefix = getattr(rule, "path_prefix", None)
    if path_prefix and not path.casefold().startswith(str(path_prefix).casefold()):
        return False
    expected_account = getattr(rule, "account", None)
    return (
        not expected_account
        or (account or "").casefold() == str(expected_account).casefold()
    )


def canonical_claim_id(source_refs: list[str], summary: str) -> str:
    normalized = re.sub(r"\s+", " ", summary.strip().casefold())
    # The canonical ledger groups the same normalized proposition across sources.
    # Source-local provenance remains in source_refs; it is not encoded into identity.
    return "claim-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def legacy_tier_contract(tier: str) -> tuple[SourceTrustTier, ClaimStatus]:
    return _LEGACY_TIER_MAP.get(
        tier,
        (SourceTrustTier.UNVERIFIED, ClaimStatus.UNKNOWN),
    )


def legacy_evidence_tier_for(
    source_trust: SourceTrustTier | str,
    claim_status: ClaimStatus | str,
) -> str:
    trust = SourceTrustTier(source_trust)
    status = ClaimStatus(claim_status)
    if status is ClaimStatus.CONFIRMED and trust is SourceTrustTier.PRIMARY_OFFICIAL:
        return "official_confirmed"
    if status is ClaimStatus.OFFICIAL_OBSERVATION:
        return "official_observation"
    if status is ClaimStatus.LEAK:
        return "leak_authenticated"
    if status is ClaimStatus.INFERENCE:
        return "inference"
    if status is ClaimStatus.SPECULATION:
        return "speculation"
    if status is ClaimStatus.AUTHOR_OPINION:
        return "author_opinion"
    if status is ClaimStatus.GAMEPLAY_OBSERVATION:
        return "gameplay_note"
    if trust is SourceTrustTier.RELIABLE_SECONDARY:
        return "reliable_secondary"
    return "unverified"


def canonical_claim_from_raw(raw: dict[str, Any]) -> PlannedClaimOutput:
    source_refs = [
        str(item)
        for item in raw.get("source_refs")
        or ([raw.get("source_fragment_id")] if raw.get("source_fragment_id") else [])
    ]
    summary = str(raw.get("summary") or "").strip()
    legacy_tier = str(raw.get("evidence_tier") or "unverified")
    mapped_trust, mapped_status = legacy_tier_contract(legacy_tier)
    source_trust = SourceTrustTier(raw.get("source_trust") or mapped_trust)
    claim_status = ClaimStatus(raw.get("claim_status") or mapped_status)
    evidence_tier = legacy_evidence_tier_for(source_trust, claim_status)
    return PlannedClaimOutput.model_validate(
        {
            "id": str(raw.get("id") or canonical_claim_id(source_refs, summary)),
            "summary": summary,
            "evidence_tier": evidence_tier,
            "source_refs": source_refs,
            "confidence": float(raw.get("confidence") or 0),
            "source_trust": source_trust.value,
            "claim_status": claim_status.value,
            "qualification": raw.get("qualification"),
            "support_scope": raw.get("support_scope"),
            "contradicting_source_refs": [
                str(item) for item in raw.get("contradicting_source_refs") or []
            ],
            "legacy_evidence_tier": legacy_tier,
        }
    )


def build_canonical_claim_ledger(
    evidence_dossier: dict[str, Any],
) -> list[PlannedClaimOutput]:
    claims: dict[str, PlannedClaimOutput] = {}
    for raw in evidence_dossier.get("claims") or []:
        claim = canonical_claim_from_raw(raw)
        current = claims.get(claim.id)
        if current is None:
            claims[claim.id] = claim
            continue
        merged_refs = list(dict.fromkeys([*current.source_refs, *claim.source_refs]))
        trust_rank = {
            "unverified": 0,
            "community": 1,
            "reliable_secondary": 2,
            "gameplay_evidence": 3,
            "human_author": 3,
            "primary_official": 4,
        }
        strongest_trust = max(
            (current.source_trust, claim.source_trust), key=trust_rank.__getitem__
        )
        status_rank = {
            status.value: index
            for index, status in enumerate(_CLAIM_STATUS_CONSERVATIVE_ORDER)
        }
        conservative_status = min(
            (current.claim_status, claim.claim_status), key=status_rank.__getitem__
        )
        contradictions = sorted(
            {
                *current.contradicting_source_refs,
                *claim.contradicting_source_refs,
            }
        )
        same_status = current.claim_status == claim.claim_status
        confidence = (
            max(current.confidence, claim.confidence)
            if same_status and not contradictions
            else min(current.confidence, claim.confidence)
        )
        if contradictions:
            confidence = min(confidence, 0.5)
        qualifications = sorted(
            {
                text.strip()
                for text in [current.qualification, claim.qualification]
                if text and text.strip()
            }
        )
        if current.claim_status != claim.claim_status:
            qualifications.append(
                "Fontes de apoio atribuem status epistêmicos diferentes; o ledger "
                "preserva o status mais conservador."
            )
        support_scopes = sorted(
            {
                text.strip()
                for text in [current.support_scope, claim.support_scope]
                if text and text.strip()
            }
        )
        evidence_tier = legacy_evidence_tier_for(strongest_trust, conservative_status)
        claims[claim.id] = current.model_copy(
            update={
                "source_refs": merged_refs,
                "source_trust": strongest_trust,
                "claim_status": conservative_status,
                "evidence_tier": evidence_tier,
                "legacy_evidence_tier": evidence_tier,
                "confidence": confidence,
                "qualification": " ".join(qualifications)[:1000] or None,
                "support_scope": " | ".join(support_scopes)[:1000] or None,
                "contradicting_source_refs": contradictions,
            }
        )
    return [claims[key] for key in sorted(claims)]
