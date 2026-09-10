from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.schemas.manual_script_import import ManualScriptImportResponse


def payload() -> dict:
    return {
        "ideia_id": str(uuid4()),
        "source_filename": "roteiro.json",
        "script": {
            "schema": "neovids_manual_script_v1",
            "title": "Roteiro manual",
            "blocks": [{"type": "abertura", "text": "Narração exata."}],
        },
    }


def script_response(*, revision_kind: str = "manual_create", version: int = 1) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(uuid4()),
        "ideia_id": str(uuid4()),
        "versao": version,
        "estrutura": {
            "titulo": "Roteiro manual",
            "duracao_total_segundos": 10,
            "blocos": [
                {
                    "tipo": "abertura",
                    "duracao_segundos": 10,
                    "conteudo": "Narração exata.",
                    "visual_queries": [],
                }
            ],
            "tags": [],
        },
        "status": "rascunho",
        "author_briefing_snapshot": "Contexto do autor",
        "author_briefing_identity": "author-briefing-test",
        "author_briefing_changed_since_creation": False,
        "parent_roteiro_id": None,
        "revision_kind": revision_kind,
        "revision_feedback": None,
        "criado_em": now,
        "atualizado_em": now,
    }


def preview_response(request_payload: dict) -> dict:
    return {
        "importable": True,
        "schema_version": "neovids_manual_script_v1",
        "idea": {
            "id": request_payload["ideia_id"],
            "title": "Idea",
            "niche": "Games",
            "production_profile": "game_analysis",
            "target_duration_seconds": 120,
            "duration_mode": "explicit_target",
        },
        "normalized": {
            "title": "Roteiro manual",
            "block_count": 1,
            "word_count": 2,
            "duration_total_seconds": 10,
            "normalized_payload_sha256": "a" * 64,
            "blocks": [
                {
                    "index": 0,
                    "type": "abertura",
                    "word_count": 2,
                    "duration_seconds": 10,
                    "duration_source": "estimated",
                }
            ],
        },
        "duration": {"status": "below_target"},
        "media_scope": {
            "provided": False,
            "project_id": None,
            "session_ids": [],
            "scope": "not_provided",
        },
        "visual": {"status": "pending_enrichment", "message": "pending"},
        "production_readiness": {"expected_status_after_import": "not_ready"},
        "warnings": ["warning"],
        "errors": [],
    }


def test_preview_endpoint_validates_without_persisting() -> None:
    request_payload = payload()
    generator = AsyncMock()
    generator.preview_manual_import.return_value = preview_response(request_payload)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.services.roteiros.gerador_roteiro.get_roteiro_generator",
                return_value=generator,
            ),
            TestClient(app) as client,
        ):
            response = client.post("/roteiros/importar/preview", json=request_payload)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["importable"] is True
    generator.preview_manual_import.assert_awaited_once()
    generator.import_manual_script.assert_not_awaited()


def test_unknown_external_field_is_rejected_at_the_http_boundary() -> None:
    request_payload = payload()
    request_payload["script"]["visual_queries"] = []
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with TestClient(app) as client:
            response = client.post("/roteiros/importar/preview", json=request_payload)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "visual_queries"


def test_missing_idea_is_a_clear_404() -> None:
    generator = AsyncMock()
    generator.preview_manual_import.side_effect = ValueError("Ideia não encontrada")
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.services.roteiros.gerador_roteiro.get_roteiro_generator",
                return_value=generator,
            ),
            TestClient(app) as client,
        ):
            response = client.post("/roteiros/importar/preview", json=payload())
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json() == {"detail": "Ideia não encontrada"}


def test_duplicate_import_returns_200_and_the_existing_revision() -> None:
    request_payload = payload()
    draft = script_response()
    draft["ideia_id"] = request_payload["ideia_id"]
    generator = AsyncMock()
    generator.import_manual_script.return_value = (
        ManualScriptImportResponse.model_validate(
            {
                "created": False,
                "duplicate": True,
                "normalized_payload_sha256": "a" * 64,
                "draft": draft,
                "current_revision": draft,
                "media_binding_applied": False,
            }
        )
    )
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.services.roteiros.gerador_roteiro.get_roteiro_generator",
                return_value=generator,
            ),
            TestClient(app) as client,
        ):
            response = client.post("/roteiros/importar", json=request_payload)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["duplicate"] is True
    assert response.json()["draft"]["revision_kind"] == "manual_create"


def test_runtime_import_chain_exposes_the_canonical_duration_predictor() -> None:
    from app.api.routers.roteiros import router
    from app.services.duration_contract import predict_duration_seconds
    from app.services.manual_script_import import normalize_manual_script
    from app.services.roteiros.gerador_roteiro import RoteiroGenerator

    assert router is not None
    assert callable(predict_duration_seconds)
    assert callable(normalize_manual_script)
    assert RoteiroGenerator is not None


def test_blocked_approval_is_a_controlled_business_error() -> None:
    script_id = uuid4()
    generator = AsyncMock()
    generator.aprovar_roteiro.side_effect = ValueError(
        "Aprovação bloqueada pela revisão editorial "
        "(editorial_status=needs_revision, factuality_status=blocking)"
    )
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.services.roteiros.gerador_roteiro.get_roteiro_generator",
                return_value=generator,
            ),
            TestClient(app) as client,
        ):
            response = client.patch(f"/roteiros/{script_id}/aprovar")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Aprovação bloqueada")


def test_non_blocked_approval_endpoint_still_returns_the_script() -> None:
    script_id = uuid4()
    approved = script_response()
    approved["id"] = str(script_id)
    approved["status"] = "aprovado"
    generator = AsyncMock()
    repository = AsyncMock()
    repository.get_by_id.return_value = approved
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.services.roteiros.gerador_roteiro.get_roteiro_generator",
                return_value=generator,
            ),
            patch(
                "app.api.routers.roteiros.RoteiroRepository",
                return_value=repository,
            ),
            TestClient(app) as client,
        ):
            response = client.patch(f"/roteiros/{script_id}/aprovar")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["id"] == str(script_id)
    assert response.json()["status"] == "aprovado"
    generator.aprovar_roteiro.assert_awaited_once_with(script_id)
