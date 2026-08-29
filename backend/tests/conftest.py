"""
Fixtures para testes do ideas-hub.
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    """Mock da sessão do SQLAlchemy."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_ideia_repo():
    """Mock do repositório de ideias."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.find_similar = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_nicho_repo():
    """Mock do repositório de nichos."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock()
    return repo


@pytest.fixture
def mock_roteiro_repo():
    """Mock do repositório de roteiros."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.get_latest_version_by_ideia = AsyncMock()
    return repo


@pytest.fixture
def mock_trend_repo():
    """Mock do repositório de trends."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock()
    return repo


@pytest.fixture
def mock_httpx_client():
    """Mock do cliente HTTP."""
    with patch("httpx.AsyncClient") as mock_client:
        client_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = client_instance

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": '{"titulo": "Teste", "descricao": "Descricao teste"}'}}],
            "usage": {"total_tokens": 100}
        }
        response.raise_for_status = MagicMock()
        client_instance.post = AsyncMock(return_value=response)

        yield client_instance


@pytest.fixture
def mock_tavily_response():
    """Mock de resposta do Tavily."""
    return {
        "answer": "Resposta de teste",
        "results": [
            {"title": "Resultado 1", "content": "Conteúdo do resultado 1"},
            {"title": "Resultado 2", "content": "Conteúdo do resultado 2"},
        ]
    }


@pytest.fixture
def sample_ideia_bruta():
    """Ideia bruta de exemplo."""
    from app.agents.curador import IdeiaBruta
    return IdeiaBruta(
        titulo="Como usar IA para criar vídeos",
        descricao="Tutorial prático para iniciantes",
        nicho_id=str(uuid4()),
        origem="manual"
    )


@pytest.fixture
def sample_nicho():
    """Nicho de exemplo."""
    nicho = MagicMock()
    nicho.id = uuid4()
    nicho.nome = "Tecnologia"
    nicho.slug = "tecnologia"
    nicho.prompt_ideacao = "Crie ideias sobre tecnologia"
    nicho.prompt_roteiro = "Crie roteiros técnicos"
    return nicho


@pytest.fixture
def sample_ideia():
    """Ideia de exemplo."""
    ideia = MagicMock()
    ideia.id = uuid4()
    ideia.titulo = "Como usar IA para criar vídeos"
    ideia.descricao_breve = "Tutorial prático para iniciantes"
    ideia.author_briefing = None
    ideia.author_briefing_identity = "author-briefing-v1:test"
    ideia.status = "aprovada"
    ideia.nicho_id = uuid4()
    ideia.numero_parte = None
    ideia.eh_continuacao_de = None
    return ideia
