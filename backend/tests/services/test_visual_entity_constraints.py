import pytest

from app.services.visual_entity_constraints import validate_visual_query_entity_scope


def test_numbered_work_drift_is_rejected_without_product_hardcoding() -> None:
    with pytest.raises(ValueError, match="entity drift"):
        validate_visual_query_entity_scope(
            query="Clipes de gameplay de GTA V mostrando a física",
            authorized_context="Análise da física de GTA IV.",
        )


def test_explicit_comparison_allows_both_numbered_works() -> None:
    validate_visual_query_entity_scope(
        query="Comparação da física de GTA IV e GTA V",
        authorized_context="Compare a física de GTA IV com GTA V.",
    )
