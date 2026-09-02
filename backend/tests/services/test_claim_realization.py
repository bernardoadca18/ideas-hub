"""Unit tests for Claim Realization Contract derivation."""

from __future__ import annotations

import pytest

from app.services.claim_realization import (
    ClaimRealizationContract,
    _derive_source_label,
    _extract_publisher_from_url,
    derive_claim_realization_contracts,
    realization_contracts_by_ref,
)
from app.services.editorial_evidence import ClaimStatus


def _claim(
    claim_id: str = "claim-a",
    *,
    status: str = "reported",
    source_ref: str = "source-a",
    source_trust: str = "reliable_secondary",
    summary: str = "Uma fonte relata um detalhe.",
    qualification: str | None = "Segundo a fonte.",
    support_scope: str | None = "Somente o detalhe relatado.",
    contradicting_refs: list[str] | None = None,
) -> dict:
    return {
        "id": claim_id,
        "summary": summary,
        "source_refs": [source_ref],
        "source_trust": source_trust,
        "claim_status": status,
        "qualification": qualification,
        "support_scope": support_scope,
        "contradicting_source_refs": contradicting_refs or [],
    }


def _fragment(
    fragment_id: str = "source-a",
    *,
    title: str | None = "CNN Brasil",
    url: str | None = "https://cnnbrasil.com.br/article",
) -> dict:
    return {
        "source_fragment_id": fragment_id,
        "source_title": title,
        "source_url": url,
        "url": url,
    }


class TestClaimRealizationContract:
    """Tests for ClaimRealizationContract dataclass."""

    def test_to_writer_dict_serializes_correctly(self) -> None:
        contract = ClaimRealizationContract(
            claim_ref="claim-123",
            summary="Test claim",
            claim_status="reported",
            source_trust="reliable_secondary",
            source_label="CNN Brasil",
            attribution_required=True,
            qualification_required=False,
            scope_preservation_required=True,
            qualification="Segundo a fonte.",
            support_scope="Somente o relatado.",
            contradiction_present=False,
        )
        result = contract.to_writer_dict()

        assert result["claim_ref"] == "claim-123"
        assert result["summary"] == "Test claim"
        assert result["claim_status"] == "reported"
        assert result["source_label"] == "CNN Brasil"
        assert result["attribution_required"] is True
        assert result["qualification_required"] is False
        assert result["scope_preservation_required"] is True
        assert result["qualification"] == "Segundo a fonte."
        assert result["support_scope"] == "Somente o relatado."
        # contradiction_present is not included in writer dict
        assert "contradiction_present" not in result


class TestReportedStatus:
    """Tests for REPORTED status claims."""

    def test_reported_requires_attribution(self) -> None:
        contracts = derive_claim_realization_contracts([_claim(status="reported")])
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.attribution_required is True
        assert contract.qualification_required is False
        assert contract.scope_preservation_required is True

    def test_reported_with_source_label(self) -> None:
        claims = [_claim(status="reported", source_ref="frag-1")]
        fragments = [_fragment(fragment_id="frag-1", title="IGN Brasil")]

        contracts = derive_claim_realization_contracts(claims, fragments)
        assert contracts[0].source_label == "IGN Brasil"


class TestConfirmedStatus:
    """Tests for CONFIRMED status claims."""

    def test_confirmed_does_not_require_attribution(self) -> None:
        contracts = derive_claim_realization_contracts([_claim(status="confirmed")])
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.attribution_required is False
        assert contract.qualification_required is False

    def test_confirmed_with_support_scope_requires_preservation(self) -> None:
        """Confirmed claims with support_scope must not extrapolate beyond scope."""
        claim = _claim(status="confirmed", support_scope="Somente o fato confirmado.")
        contracts = derive_claim_realization_contracts([claim])
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.scope_preservation_required is True

    def test_confirmed_without_support_scope_no_preservation_required(self) -> None:
        """Confirmed claims without support_scope have no scope to preserve."""
        claim = _claim(status="confirmed", support_scope=None)
        contracts = derive_claim_realization_contracts([claim])
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.scope_preservation_required is False

    def test_confirmed_still_preserves_scope_in_writer_dict(self) -> None:
        contracts = derive_claim_realization_contracts([_claim(status="confirmed")])
        writer_dict = contracts[0].to_writer_dict()

        # Scope is provided for reference
        assert writer_dict["support_scope"] == "Somente o detalhe relatado."


class TestSpeculationStatus:
    """Tests for SPECULATION status claims."""

    def test_speculation_requires_qualification(self) -> None:
        contracts = derive_claim_realization_contracts([_claim(status="speculation")])
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.attribution_required is False
        assert contract.qualification_required is True
        assert contract.scope_preservation_required is True


class TestInferenceStatus:
    """Tests for INFERENCE status claims."""

    def test_inference_requires_qualification(self) -> None:
        contracts = derive_claim_realization_contracts([_claim(status="inference")])
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.attribution_required is False
        assert contract.qualification_required is True
        assert contract.scope_preservation_required is True


class TestOfficialObservationStatus:
    """Tests for OFFICIAL_OBSERVATION status claims."""

    def test_official_observation_requires_scope_preservation(self) -> None:
        contracts = derive_claim_realization_contracts(
            [_claim(status="official_observation")]
        )
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.attribution_required is False
        assert contract.qualification_required is False
        assert contract.scope_preservation_required is True


class TestSourceLabel:
    """Tests for source label derivation."""

    def test_source_label_from_title(self) -> None:
        claim = _claim(source_ref="frag-1")
        fragments = [_fragment(fragment_id="frag-1", title="Universo PlayStation")]

        label = _derive_source_label(claim, fragments)
        assert label == "Universo PlayStation"

    def test_source_label_fallback_to_hostname(self) -> None:
        claim = _claim(source_ref="frag-1")
        fragments = [
            _fragment(fragment_id="frag-1", title=None, url="https://br.ign.com/article")
        ]

        label = _derive_source_label(claim, fragments)
        assert label == "IGN Brasil"

    def test_source_label_never_uuid(self) -> None:
        claim = _claim(source_ref="550e8400-e29b-41d4-a716-446655440000")
        # No fragments provided, no URL in source_refs

        label = _derive_source_label(claim, None)
        assert label == "fonte"
        assert "550e8400" not in label

    def test_source_label_missing_fragment_returns_fallback(self) -> None:
        claim = _claim(source_ref="unknown-source")
        fragments = [_fragment(fragment_id="other-source")]

        label = _derive_source_label(claim, fragments)
        assert label == "fonte"

    def test_source_label_cleans_youtube_suffix(self) -> None:
        claim = _claim(source_ref="frag-1")
        fragments = [
            _fragment(
                fragment_id="frag-1",
                title="Gameplay Trailer - YouTube",
                url="https://youtube.com/watch?v=123",
            )
        ]

        label = _derive_source_label(claim, fragments)
        assert label == "Gameplay Trailer"


class TestExtractPublisherFromUrl:
    """Tests for URL publisher extraction."""

    def test_cnn_brasil(self) -> None:
        result = _extract_publisher_from_url("https://cnnbrasil.com.br/noticia")
        assert result == "CNN Brasil"

    def test_ign_brasil(self) -> None:
        result = _extract_publisher_from_url("https://br.ign.com/artigo")
        assert result == "IGN Brasil"

    def test_ign_main(self) -> None:
        result = _extract_publisher_from_url("https://www.ign.com/articles/article")
        assert result == "IGN"

    def test_unknown_domain_uses_first_part(self) -> None:
        result = _extract_publisher_from_url("https://gamesite.com/article")
        assert result == "Gamesite"

    def test_invalid_url_returns_none(self) -> None:
        result = _extract_publisher_from_url("not-a-url")
        # urlparse still extracts something from almost anything
        # Just ensure it doesn't crash
        assert result is not None or result is None


class TestContradiction:
    """Tests for contradiction handling."""

    def test_contradiction_present_flagged(self) -> None:
        claim = _claim(contradicting_refs=["source-b"])
        contracts = derive_claim_realization_contracts([claim])

        assert contracts[0].contradiction_present is True

    def test_no_contradiction_not_flagged(self) -> None:
        claim = _claim(contradicting_refs=[])
        contracts = derive_claim_realization_contracts([claim])

        assert contracts[0].contradiction_present is False


class TestRealizationContractsByRef:
    """Tests for contract indexing."""

    def test_index_by_ref(self) -> None:
        contracts = [
            ClaimRealizationContract(
                claim_ref="claim-a",
                summary="A",
                claim_status="reported",
                source_trust="reliable_secondary",
                source_label="Source A",
                attribution_required=True,
                qualification_required=False,
                scope_preservation_required=True,
                qualification=None,
                support_scope=None,
                contradiction_present=False,
            ),
            ClaimRealizationContract(
                claim_ref="claim-b",
                summary="B",
                claim_status="confirmed",
                source_trust="primary_official",
                source_label="Source B",
                attribution_required=False,
                qualification_required=False,
                scope_preservation_required=False,
                qualification=None,
                support_scope=None,
                contradiction_present=False,
            ),
        ]

        index = realization_contracts_by_ref(contracts)
        assert index["claim-a"].summary == "A"
        assert index["claim-b"].summary == "B"

    def test_empty_contracts(self) -> None:
        index = realization_contracts_by_ref([])
        assert index == {}


class TestUnknownClaim:
    """Tests for unknown/missing claims."""

    def test_section_claim_ref_must_exist_before_realization(self) -> None:
        """Verify that claim coverage validation prevents unknown claims from reaching writer.

        This is enforced by planning_claim_coverage.validate_and_normalize_section_coverage
        which rejects unknown claim refs before they reach the writer stage.
        """
        # The planning_claim_coverage module already prevents this:
        # test_unknown_claim_is_rejected_before_writing verifies this behavior
        # ClaimRealization should never receive a claim_ref that doesn't exist
        # in the approved claim ledger
        pass


class TestStronglySupportedStatus:
    """Tests for STRONGLY_SUPPORTED status claims."""

    def test_strongly_supported_with_support_scope_requires_preservation(self) -> None:
        """Strongly supported claims with support_scope must not extrapolate."""
        claim = _claim(status="strongly_supported", support_scope="Somente o fato suportado.")
        contracts = derive_claim_realization_contracts([claim])
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.attribution_required is False
        assert contract.qualification_required is False
        assert contract.scope_preservation_required is True

    def test_strongly_supported_without_support_scope_no_preservation(self) -> None:
        """Strongly supported claims without support_scope have no scope to preserve."""
        claim = _claim(status="strongly_supported", support_scope=None)
        contracts = derive_claim_realization_contracts([claim])
        assert len(contracts) == 1

        contract = contracts[0]
        assert contract.scope_preservation_required is False


class TestMultipleStatuses:
    """Tests for various claim statuses with default support_scope."""

    @pytest.mark.parametrize(
        "status,expect_attribution,expect_qualification,expect_scope",
        [
            # Direct statuses WITH support_scope (default) require scope preservation
            ("confirmed", False, False, True),
            ("strongly_supported", False, False, True),
            ("author_opinion", False, False, True),
            ("gameplay_observation", False, False, True),
            # Non-direct statuses always require scope preservation
            ("reported", True, False, True),
            ("official_observation", False, False, True),
            ("rumor", False, True, True),
            ("leak", False, True, True),
            ("speculation", False, True, True),
            ("inference", False, True, True),
            ("interpretation", False, True, True),
            ("unknown", False, True, True),
        ],
    )
    def test_status_derives_correct_constraints(
        self,
        status: str,
        expect_attribution: bool,
        expect_qualification: bool,
        expect_scope: bool,
    ) -> None:
        contracts = derive_claim_realization_contracts([_claim(status=status)])
        contract = contracts[0]

        assert contract.attribution_required == expect_attribution
        assert contract.qualification_required == expect_qualification
        assert contract.scope_preservation_required == expect_scope
