from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agents.curador import IdeiaRefinada
from app.api.routers.ideias import get_ideia_repo, get_nicho_repo
from app.main import app
from app.services.author_briefing import author_briefing_identity


def idea_record(briefing: str | None):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(), nicho_id=None, origem="manual", titulo="Ideia refinada",
        descricao_breve="Descrição refinada", author_briefing=briefing,
        author_briefing_identity=author_briefing_identity(briefing), perfil_producao=None,
        status="rascunho",
        eh_continuacao_de=None, numero_parte=None, fonte_trend_id=None,
        justificativa_llm="ok", criado_em=now, atualizado_em=now,
    )


def test_author_briefing_create_and_update_preserve_verbatim_content() -> None:
    original = "  Minha tese\r\nNão transformar opinião em fato.  "
    edited = "Nova posição\ncom contexto adicional.\n"
    repository = AsyncMock()
    created = idea_record(original)
    repository.find_similar.return_value = []
    repository.create.return_value = created
    repository.get_by_id.return_value = created

    async def update(_, payload):
        return idea_record(payload.author_briefing)

    repository.update.side_effect = update
    app.dependency_overrides[get_ideia_repo] = lambda: repository
    app.dependency_overrides[get_nicho_repo] = lambda: AsyncMock()
    try:
        with (
            patch(
                "app.api.routers.ideias.embedding_service.generate_for_ideia",
                AsyncMock(return_value=[0.0] * 1024),
            ),
            patch(
                "app.api.routers.ideias.curador_service.processar",
                AsyncMock(
                    return_value=IdeiaRefinada(
                        titulo="Ideia refinada",
                        descricao_breve="Descrição refinada",
                        justificativa_llm="ok",
                    )
                ),
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/ideias/",
                json={"titulo": "Bruta", "descricao": "Descrição", "author_briefing": original},
            )
            assert response.status_code == 201, response.text
            assert response.json()["author_briefing"] == original
            persisted = repository.create.await_args.args[0]
            assert persisted.author_briefing == original

            response = client.put(
                f"/ideias/{created.id}", json={"author_briefing": edited}
            )
            assert response.status_code == 200, response.text
            assert response.json()["author_briefing"] == edited
            assert repository.update.await_args.args[1].author_briefing == edited
    finally:
        app.dependency_overrides.clear()
