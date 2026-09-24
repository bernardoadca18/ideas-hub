from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.routers.ideias import IdeiaBrutaInput, create_ideia


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["gamedev_manual", "pov_storyboard"])
async def test_manual_production_creates_editorial_entity_without_llm(profile):
    idea_id, niche_id = uuid4(), uuid4()
    created = SimpleNamespace(id=idea_id)
    ideas = SimpleNamespace(
        create=AsyncMock(return_value=created),
        get_by_id=AsyncMock(return_value=created),
    )
    niches = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                perfil_producao=profile,
                prompt_ideacao=None,
            )
        )
    )
    with patch(
        "app.api.routers.ideias.embedding_service.generate_for_ideia",
        AsyncMock(side_effect=AssertionError("LLM unavailable")),
    ):
        result = await create_ideia(
            IdeiaBrutaInput(
                titulo="Manual production",
                nicho_id=niche_id,
                duration_mode="content_driven",
            ),
            ideas,
            niches,
        )
    assert result.id == idea_id
    assert ideas.create.call_args.args[0].titulo == "Manual production"
