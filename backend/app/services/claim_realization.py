"""Host-owned claim realization contracts for Editorial V3 writer constraints.

This module converts approved claims into explicit epistemic writing constraints.
The writer receives deterministic rules for how each claim can be narrated,
preventing loss of attribution, qualification, and support scope.

Contract: PLANNER decides WHAT claim to cover.
          HOST decides HOW that claim is allowed to be stated epistemically.
          WRITER decides HOW to say it naturally.
          AUDIT verifies what was actually said.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.services.editorial_evidence import ClaimStatus

CLAIM_REALIZATION_VERSION = "claim_realization_v1"


@dataclass(frozen=True)
class ClaimRealizationContract:
    """Deterministic epistemic constraints for narrating a single claim.

    The host derives these constraints from claim metadata; the LLM never decides
    attribution, qualification, or scope requirements.
    """

    claim_ref: str
    summary: str

    # Epistemic classification
    claim_status: str
    source_trust: str

    # Human-readable source identifier for attribution
    source_label: str

    # Derived constraints (host-owned, not LLM-inferred)
    attribution_required: bool
    qualification_required: bool
    scope_preservation_required: bool

    # Original claim metadata for writer reference
    qualification: str | None
    support_scope: str | None

    # Contradiction flag for complex cases
    contradiction_present: bool

    def to_writer_dict(self) -> dict[str, Any]:
        """Serialize for inclusion in writer prompt."""
        return {
            "claim_ref": self.claim_ref,
            "summary": self.summary,
            "claim_status": self.claim_status,
            "source_label": self.source_label,
            "attribution_required": self.attribution_required,
            "qualification_required": self.qualification_required,
            "scope_preservation_required": self.scope_preservation_required,
            "qualification": self.qualification,
            "support_scope": self.support_scope,
        }


# Status categories that require explicit attribution
_ATTRIBUTION_REQUIRED_STATUSES = {
    ClaimStatus.REPORTED.value,
}

# Status categories that require qualification language
_QUALIFICATION_REQUIRED_STATUSES = {
    ClaimStatus.RUMOR.value,
    ClaimStatus.LEAK.value,
    ClaimStatus.SPECULATION.value,
    ClaimStatus.INFERENCE.value,
    ClaimStatus.INTERPRETATION.value,
    ClaimStatus.UNKNOWN.value,
}

# Status categories with direct realization (within scope)
_DIRECT_STATUSES = {
    ClaimStatus.CONFIRMED.value,
    ClaimStatus.STRONGLY_SUPPORTED.value,
    ClaimStatus.AUTHOR_OPINION.value,
    ClaimStatus.GAMEPLAY_OBSERVATION.value,
}

# Status categories requiring scope preservation
_SCOPE_PRESERVATION_STATUSES = {
    ClaimStatus.OFFICIAL_OBSERVATION.value,
}


def _derive_source_label(
    claim: dict[str, Any],
    evidence_fragments: list[dict[str, Any]] | None = None,
) -> str:
    """Derive a human-readable source label for attribution.

    Priority:
    1. Source title/editorial label from fragment
    2. Publisher/site name from fragment
    3. Normalized hostname as fallback

    Never returns UUID or raw source ID.
    """
    source_refs = claim.get("source_refs") or []
    if not source_refs:
        return "fonte não identificada"

    # Try to find matching evidence fragment for label
    if evidence_fragments:
        for ref in source_refs:
            for fragment in evidence_fragments:
                if str(fragment.get("source_fragment_id")) == str(ref):
                    # Priority 1: source title
                    title = fragment.get("source_title")
                    if title and isinstance(title, str) and len(title.strip()) > 0:
                        # Clean up common patterns
                        cleaned = title.strip()
                        # Remove common suffixes
                        for suffix in [
                            " - YouTube",
                            " | YouTube",
                            " - Twitch",
                            " | Twitch",
                        ]:
                            cleaned = cleaned.removesuffix(suffix)
                        if len(cleaned) > 2:
                            return cleaned

                    # Priority 2: publisher/site name could be extracted from URL
                    url = fragment.get("source_url") or fragment.get("url")
                    if url:
                        hostname = _extract_publisher_from_url(url)
                        if hostname:
                            return hostname

    # Fallback: try to get from source_refs directly if they contain URLs
    for ref in source_refs:
        if isinstance(ref, str) and ref.startswith("http"):
            hostname = _extract_publisher_from_url(ref)
            if hostname:
                return hostname

    return "fonte"


def _extract_publisher_from_url(url: str) -> str | None:
    """Extract a human-readable publisher name from URL.

    Returns normalized hostname without www prefix, or None if invalid.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or parsed.netloc or ""
        if not hostname:
            return None

        # Remove www prefix
        hostname = hostname.removeprefix("www.").removeprefix("WWW.")

        # Common site mappings for better labels
        site_mappings = {
            "br.ign.com": "IGN Brasil",
            "ign.com": "IGN",
            "es.ign.com": "IGN España",
            "cnnbrasil.com.br": "CNN Brasil",
            "cnn.com": "CNN",
            "globo.com": "Globo",
            "uol.com.br": "UOL",
            "terra.com.br": "Terra",
            "folha.uol.com.br": "Folha de S.Paulo",
            "estadao.com.br": "Estadão",
            "veja.abril.com.br": "Veja",
            "reddit.com": "Reddit",
            "twitter.com": "Twitter",
            "x.com": "X",
            "youtube.com": "YouTube",
            "twitch.tv": "Twitch",
        }

        hostname_lower = hostname.lower()
        if hostname_lower in site_mappings:
            return site_mappings[hostname_lower]

        # Check for partial matches (subdomains)
        for key, value in site_mappings.items():
            if hostname_lower.endswith(key) or hostname_lower == key:
                return value

        # Capitalize first letter of each part
        parts = hostname.split(".")
        if len(parts) >= 1:
            return parts[0].capitalize()

        return None
    except (ValueError, AttributeError):
        return None


def derive_claim_realization_contracts(
    claims: list[dict[str, Any]],
    evidence_fragments: list[dict[str, Any]] | None = None,
) -> list[ClaimRealizationContract]:
    """Convert approved claims into host-owned realization contracts.

    This is the primary entry point for claim realization. Each claim
    is converted into a deterministic contract specifying how it may
    be narrated epistemically.

    Args:
        claims: List of approved claims from the canonical claim ledger.
        evidence_fragments: Optional evidence fragments for source label derivation.

    Returns:
        List of ClaimRealizationContract objects, one per claim.
    """
    contracts: list[ClaimRealizationContract] = []

    for claim in claims:
        claim_ref = str(claim.get("id") or "")
        if not claim_ref:
            continue

        status = str(claim.get("claim_status") or ClaimStatus.UNKNOWN.value)
        source_trust = str(claim.get("source_trust") or "unverified")

        # Derive source label for attribution
        source_label = _derive_source_label(claim, evidence_fragments)

        # Determine attribution requirement
        attribution_required = status in _ATTRIBUTION_REQUIRED_STATUSES

        # Determine qualification requirement
        qualification_required = status in _QUALIFICATION_REQUIRED_STATUSES

        # Determine scope preservation requirement
        # Scope must be preserved when:
        # 1. Claim has a material support_scope (regardless of status)
        # 2. Status is official_observation (explicit requirement)
        # 3. Status is non-direct (speculation, inference, etc.)
        support_scope = claim.get("support_scope")
        has_material_scope = (
            support_scope is not None
            and isinstance(support_scope, str)
            and len(support_scope.strip()) > 0
        )
        scope_preservation_required = (
            has_material_scope
            or status in _SCOPE_PRESERVATION_STATUSES
            or status not in _DIRECT_STATUSES
        )

        # Check for contradictions
        contradicting = claim.get("contradicting_source_refs") or []
        contradiction_present = len(contradicting) > 0

        contract = ClaimRealizationContract(
            claim_ref=claim_ref,
            summary=str(claim.get("summary") or ""),
            claim_status=status,
            source_trust=source_trust,
            source_label=source_label,
            attribution_required=attribution_required,
            qualification_required=qualification_required,
            scope_preservation_required=scope_preservation_required,
            qualification=claim.get("qualification"),
            support_scope=claim.get("support_scope"),
            contradiction_present=contradiction_present,
        )
        contracts.append(contract)

    return contracts


def realization_contracts_by_ref(
    contracts: list[ClaimRealizationContract],
) -> dict[str, ClaimRealizationContract]:
    """Index realization contracts by claim reference for O(1) lookup."""
    return {contract.claim_ref: contract for contract in contracts}
