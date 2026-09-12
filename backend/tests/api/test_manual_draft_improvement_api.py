from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.core.database import get_db
from app.main import app
from fastapi.testclient import TestClient


def _run_response(idea_id, *, parent_id=None) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(uuid4()),
        "ideia_id": str(idea_id),
        "roteiro_id": None,
        "parent_roteiro_id": str(parent_id) if parent_id else None,
        "generation_intent": "revision" if parent_id else "initial",
        "revision_feedback": "Preserve a comparação." if parent_id else None,
        "status": "queued",
        "phase": "planning",
        "generation_strategy": "staged",
        "production_profile": "faceless_general",
        "duration_mode": "explicit_target",
        "duration_target_source": "user",
        "target_duration_seconds": 720,
        "target_words": 1740,
        "total_sections": 3,
        "completed_sections": 0,
        "plan": {},
        "call_usage": {},
        "error_category": None,
        "error_message": None,
        "criado_em": now,
        "atualizado_em": now,
    }


def _draft_response(idea_id, draft_id, text: str) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(draft_id),
        "ideia_id": str(idea_id),
        "versao": 1,
        "estrutura": {
            "titulo": "Idea aprovada",
            "duracao_total_segundos": 10,
            "blocos": [
                {
                    "tipo": "rascunho_humano",
                    "duracao_segundos": 10,
                    "conteudo": text,
                }
            ],
            "manual_draft": {
                "adapter_version": "plain_text_manual_draft_v1",
                "source": "manual_plain_text",
                "original_text_sha256": "a" * 64,
                "original_char_count": len(text),
            },
        },
        "status": "rascunho",
        "author_briefing_snapshot": None,
        "author_briefing_identity": "briefing-id",
        "author_briefing_changed_since_creation": False,
        "parent_roteiro_id": None,
        "revision_kind": "manual_create",
        "revision_feedback": None,
        "criado_em": now,
        "atualizado_em": now,
    }


def test_initial_generation_endpoint_remains_the_same_durable_contract() -> None:
    idea_id = uuid4()
    service = AsyncMock()
    service.enqueue.return_value = _run_response(idea_id)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.api.routers.generation_runs.ScriptGenerationJobService",
                return_value=service,
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                f"/ideias/{idea_id}/generation-runs",
                json={"idempotency_key": "initial-generation-001"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["generation_intent"] == "initial"
    service.enqueue.assert_awaited_once_with(
        idea_id,
        idempotency_key="initial-generation-001",
        model_strategy="standard",
    )


def test_manual_draft_endpoint_returns_persisted_parent_and_revision_run() -> None:
    idea_id = uuid4()
    draft_id = uuid4()
    text = "Primeiro parágrafo.\n\nSegundo parágrafo preservado."
    run = _run_response(idea_id, parent_id=draft_id)
    service = AsyncMock()
    service.enqueue_manual_draft_improvement.return_value = {
        "created": True,
        "duplicate": False,
        "draft": _draft_response(idea_id, draft_id, text),
        "run": run,
    }
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.api.routers.generation_runs.ScriptGenerationJobService",
                return_value=service,
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                f"/ideias/{idea_id}/manual-draft-improvement-runs",
                json={
                    "draft_text": text,
                    "feedback": "  Preserve a comparação.  ",
                    "idempotency_key": "manual-improvement-001",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload["draft"]["estrutura"]["blocos"][0]["conteudo"] == text
    assert payload["draft"]["revision_kind"] == "manual_create"
    assert payload["run"]["generation_intent"] == "revision"
    assert payload["run"]["parent_roteiro_id"] == str(draft_id)
    service.enqueue_manual_draft_improvement.assert_awaited_once_with(
        idea_id,
        draft_text=text,
        idempotency_key="manual-improvement-001",
        feedback="Preserve a comparação.",
        model_strategy="standard",
    )


def test_manual_draft_endpoint_rejects_blank_text_before_service_work() -> None:
    idea_id = uuid4()
    service = AsyncMock()
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.api.routers.generation_runs.ScriptGenerationJobService",
                return_value=service,
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                f"/ideias/{idea_id}/manual-draft-improvement-runs",
                json={
                    "draft_text": " \n\t ",
                    "idempotency_key": "manual-improvement-002",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    service.enqueue_manual_draft_improvement.assert_not_awaited()

