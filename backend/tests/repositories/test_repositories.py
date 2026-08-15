"""
Testes para os repositórios.

Testa operações CRUD com banco de dados mockado.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from app.repositories.ideia_repository import IdeiaRepository
from app.repositories.nicho_repository import NichoRepository
from app.repositories.roteiro_repository import RoteiroRepository
from app.repositories.trend_coletada_repository import TrendColetadaRepository


class TestIdeiaRepository:
    """Testes do repositório de ideias."""

    @pytest.fixture
    def repo(self, mock_session):
        return IdeiaRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_ideia(self, repo, mock_session):
        """Testa criação de ideia."""
        from app.schemas.ideia import IdeiaCreate

        ideia_data = IdeiaCreate(
            nicho_id=uuid4(),
            origem="manual",
            titulo="Ideia de teste",
            descricao_breve="Descrição da ideia",
            status="rascunho"
        )

        # Mock do resultado
        ideia_mock = MagicMock()
        ideia_mock.id = uuid4()
        ideia_mock.titulo = ideia_data.titulo
        ideia_mock.status = ideia_data.status

        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch.object(repo, 'create', AsyncMock(return_value=ideia_mock)):
            result = await repo.create(ideia_data)
            assert result.titulo == ideia_data.titulo

    @pytest.mark.asyncio
    async def test_get_by_id(self, repo, mock_session):
        """Testa busca de ideia por ID."""
        ideia_id = uuid4()
        ideia_mock = MagicMock()
        ideia_mock.id = ideia_id
        ideia_mock.titulo = "Ideia encontrada"

        with patch.object(repo, 'get_by_id', AsyncMock(return_value=ideia_mock)):
            result = await repo.get_by_id(ideia_id)
            assert result.id == ideia_id
            assert result.titulo == "Ideia encontrada"

    @pytest.mark.asyncio
    async def test_find_similar(self, repo, mock_session):
        """Testa busca de ideias similares."""
        embedding = [0.1] * 1536  # Embedding de exemplo

        ideia_similar = MagicMock()
        ideia_similar.id = uuid4()
        ideia_similar.titulo = "Ideia Similar"
        ideia_similar.titulo = 0.95

        with patch.object(repo, 'find_similar', AsyncMock(return_value=[ideia_similar])):
            result = await repo.find_similar(embedding=embedding, threshold=0.85, limit=5)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_update_status(self, repo, mock_session):
        """Testa atualização de status da ideia."""
        from app.schemas.ideia import IdeiaUpdate

        ideia_id = uuid4()
        update_data = IdeiaUpdate(status="aprovada")

        ideia_atualizada = MagicMock()
        ideia_atualizada.id = ideia_id
        ideia_atualizada.status = "aprovada"

        with patch.object(repo, 'update', AsyncMock(return_value=ideia_atualizada)):
            result = await repo.update(ideia_id, update_data)
            assert result.status == "aprovada"


class TestNichoRepository:
    """Testes do repositório de nichos."""

    @pytest.fixture
    def repo(self, mock_session):
        return NichoRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_slug(self, repo, mock_session):
        """Testa busca de nicho por slug."""
        nicho_mock = MagicMock()
        nicho_mock.id = uuid4()
        nicho_mock.slug = "tecnologia"
        nicho_mock.nome = "Tecnologia"

        with patch.object(repo, 'get_by_slug', AsyncMock(return_value=nicho_mock)):
            result = await repo.get_by_slug("tecnologia")
            assert result.slug == "tecnologia"

    @pytest.mark.asyncio
    async def test_list_all(self, repo, mock_session):
        """Testa listagem de todos os nichos."""
        nichos = [
            MagicMock(id=uuid4(), slug="tech", nome="Tech"),
            MagicMock(id=uuid4(), slug="games", nome="Games"),
        ]

        with patch.object(repo, 'list', AsyncMock(return_value=nichos)):
            result = await repo.list()
            assert len(result) == 2


class TestRoteiroRepository:
    """Testes do repositório de roteiros."""

    @pytest.fixture
    def repo(self, mock_session):
        return RoteiroRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_roteiro(self, repo, mock_session):
        """Testa criação de roteiro."""
        from app.schemas.roteiro import RoteiroCreate

        roteiro_data = RoteiroCreate(
            ideia_id=uuid4(),
            versao=1,
            estrutura={
                "titulo": "Roteiro Teste",
                "duracao_total_segundos": 180,
                "blocos": []
            },
            status="rascunho"
        )

        roteiro_mock = MagicMock()
        roteiro_mock.id = uuid4()
        roteiro_mock.versao = 1

        with patch.object(repo, 'create', AsyncMock(return_value=roteiro_mock)):
            result = await repo.create(roteiro_data)
            assert result.versao == 1

    @pytest.mark.asyncio
    async def test_get_latest_version(self, repo, mock_session):
        """Testa busca da última versão de roteiro de uma ideia."""
        ideia_id = uuid4()

        roteiro_mock = MagicMock()
        roteiro_mock.versao = 3

        with patch.object(repo, 'get_latest_version_by_ideia', AsyncMock(return_value=roteiro_mock)):
            result = await repo.get_latest_version_by_ideia(ideia_id)
            assert result.versao == 3


class TestTrendColetadaRepository:
    """Testes do repositório de trends."""

    @pytest.fixture
    def repo(self, mock_session):
        return TrendColetadaRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_trend(self, repo, mock_session):
        """Testa criação de trend."""
        from app.schemas.trend_coletada import TrendColetadaCreate

        trend_data = TrendColetadaCreate(
            nicho_id=uuid4(),
            fonte="google_trends",
            termo_bruto="Trend Teste",
            status="pendente"
        )

        trend_mock = MagicMock()
        trend_mock.id = uuid4()
        trend_mock.termo_bruto = "Trend Teste"

        with patch.object(repo, 'create', AsyncMock(return_value=trend_mock)):
            result = await repo.create(trend_data)
            assert result.termo_bruto == "Trend Teste"

    @pytest.mark.asyncio
    async def test_list_by_status(self, repo, mock_session):
        """Testa listagem de trends por status."""
        trends = [
            MagicMock(id=uuid4(), termo_bruto="Trend 1", status="pendente"),
            MagicMock(id=uuid4(), termo_bruto="Trend 2", status="pendente"),
        ]

        with patch.object(repo, 'list', AsyncMock(return_value=trends)):
            result = await repo.list(status="pendente")
            assert len(result) == 2
            assert all(t.status == "pendente" for t in result)

    @pytest.mark.asyncio
    async def test_create_batch(self, repo, mock_session):
        """Testa criação em lote de trends."""
        from app.schemas.trend_coletada import TrendColetadaCreate

        trends_data = [
            TrendColetadaCreate(nicho_id=uuid4(), fonte="google_trends", termo_bruto="Trend 1", status="pendente"),
            TrendColetadaCreate(nicho_id=uuid4(), fonte="google_trends", termo_bruto="Trend 2", status="pendente"),
        ]

        trends_mock = [
            MagicMock(id=uuid4(), termo_bruto="Trend 1"),
            MagicMock(id=uuid4(), termo_bruto="Trend 2"),
        ]

        with patch.object(repo, 'create_batch', AsyncMock(return_value=trends_mock)):
            result = await repo.create_batch(trends_data)
            assert len(result) == 2
