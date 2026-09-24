from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.nicho import Nicho
from app.schemas.manual_script_import import ManualScriptImportRequest
from app.services.duration_contract import DurationCalibration
from app.services.roteiros.gerador_roteiro import RoteiroGenerator


@pytest.mark.asyncio
async def test_new_content_preview_does_not_persist_or_require_llm():
    session = AsyncMock()
    generator = RoteiroGenerator(session, media_indexer_client=AsyncMock())
    niche = Nicho(id=uuid4(), nome="GameDev", perfil_producao="gamedev_manual")
    generator.ideia_repo.get_by_id = AsyncMock(return_value=None)
    generator.nicho_repo.get_by_id = AsyncMock(return_value=niche)
    request = ManualScriptImportRequest.model_validate(
        {
            "ideia_id": str(uuid4()),
            "new_content_niche_id": str(niche.id),
            "source_filename": "manual.json",
            "script": {
                "schema": "neovids_manual_script_v1",
                "title": "My game",
                "blocks": [{"type": "intro", "text": "I built a game."}],
            },
        }
    )
    with patch(
        "app.services.roteiros.gerador_roteiro.duration_calibration_client.get",
        AsyncMock(
            return_value=DurationCalibration.fallback_for(
                production_profile="gamedev_manual"
            )
        ),
    ):
        preview = await generator.preview_manual_import(request)
    assert preview.importable
    assert preview.idea.id == request.ideia_id
    assert preview.idea.duration_mode == "content_driven"
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()
    generator.media_indexer_client.get_project.assert_not_awaited()
