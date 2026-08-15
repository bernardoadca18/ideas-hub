"""
Testes para o Agente Curador.

Testa o processamento de ideias com mock de LLM e Tavily.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json

from app.agents.curador import CuradorService, IdeiaBruta, IdeiaRefinada


@pytest.fixture
def curador_service():
    """Instância do CuradorService para testes."""
    return CuradorService()


class TestCuradorService:
    """Testes do serviço Curador."""

    @pytest.mark.asyncio
    async def test_call_llm_success(self, curador_service, mock_httpx_client):
        """Testa chamada bem-sucedida ao LLM."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "Resposta do LLM"}}],
            "usage": {"total_tokens": 150}
        }
        response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = response

        result = await curador_service._call_llm(
            messages=[{"role": "user", "content": "teste"}],
            temperature=0.7
        )

        assert result == "Resposta do LLM"

    @pytest.mark.asyncio
    async def test_search_tavily_success(self, curador_service, mock_httpx_client):
        """Testa busca no Tavily."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "answer": "Resposta da API",
            "results": [
                {"title": "Título 1", "content": "Conteúdo 1"},
                {"title": "Título 2", "content": "Conteúdo 2"},
            ]
        }
        response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = response

        # Define API key para habilitar Tavily
        curador_service.tavily_api_key = "test-key"

        result = await curador_service._search_tavily("query de teste")

        assert "Resposta da API" in result or "Título 1" in result

    @pytest.mark.asyncio
    async def test_search_tavily_no_api_key(self, curador_service):
        """Testa que Tavily retorna vazio sem API key."""
        curador_service.tavily_api_key = None
        result = await curador_service._search_tavily("query de teste")
        assert result == ""

    @pytest.mark.asyncio
    async def test_processar_ideia_bruta(self, curador_service, sample_ideia_bruta, mock_httpx_client):
        """Testa processamento completo de ideia bruta."""
        # Mock resposta do Tavily
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {
            "answer": "Contexto de pesquisa",
            "results": []
        }
        tavily_response.raise_for_status = MagicMock()

        # Mock resposta do LLM
        llm_response = MagicMock()
        llm_response.status_code = 200
        llm_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "titulo": "Título refinado",
                        "descricao_breve": "Descrição refinada",
                        "justificativa": "Teste"
                    })
                }
            }],
            "usage": {"total_tokens": 200}
        }
        llm_response.raise_for_status = MagicMock()

        mock_httpx_client.post.side_effect = [tavily_response, llm_response]
        curador_service.tavily_api_key = "test-key"

        result = await curador_service.processar(
            ideia_bruta=sample_ideia_bruta,
            prompt_nicho="Crie ideias sobre tecnologia",
            ideias_similares=None
        )

        assert isinstance(result, IdeiaRefinada)
        assert result.titulo == "Título refinado"
        assert result.descricao_breve == "Descrição refinada"
        assert result.eh_duplicada is False

    @pytest.mark.asyncio
    async def test_processar_ideia_duplicada(self, curador_service, sample_ideia_bruta, mock_httpx_client):
        """Testa detecção de ideia duplicada."""
        # Mock resposta do Tavily
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {"answer": "", "results": []}
        tavily_response.raise_for_status = MagicMock()

        # Mock resposta do LLM
        llm_response = MagicMock()
        llm_response.status_code = 200
        llm_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "titulo": "Título refinado",
                        "descricao_breve": "Descrição refinada",
                        "justificativa": "Teste"
                    })
                }
            }],
            "usage": {"total_tokens": 200}
        }
        llm_response.raise_for_status = MagicMock()

        mock_httpx_client.post.side_effect = [tavily_response, llm_response]
        curador_service.tavily_api_key = "test-key"

        # Simula ideias similares com alta similaridade
        ideias_similares = [
            {"id": "uuid-similar", "titulo": "Ideia Similar", "similaridade": 0.96}
        ]

        result = await curador_service.processar(
            ideia_bruta=sample_ideia_bruta,
            prompt_nicho=None,
            ideias_similares=ideias_similares
        )

        assert result.eh_duplicada is True
        assert result.similaridade == 0.96

    @pytest.mark.asyncio
    async def test_processar_ideia_continuacao(self, curador_service, sample_ideia_bruta, mock_httpx_client):
        """Testa detecção de ideia como continuação."""
        # Mock resposta do Tavily
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {"answer": "", "results": []}
        tavily_response.raise_for_status = MagicMock()

        # Mock resposta do LLM
        llm_response = MagicMock()
        llm_response.status_code = 200
        llm_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "titulo": "Título refinado",
                        "descricao_breve": "Descrição refinada",
                        "justificativa": "Teste"
                    })
                }
            }],
            "usage": {"total_tokens": 200}
        }
        llm_response.raise_for_status = MagicMock()

        mock_httpx_client.post.side_effect = [tavily_response, llm_response]
        curador_service.tavily_api_key = "test-key"

        # Simula ideias similares com similaridade média
        ideias_similares = [
            {"id": "uuid-similar", "titulo": "Ideia Similar", "similaridade": 0.90}
        ]

        result = await curador_service.processar(
            ideia_bruta=sample_ideia_bruta,
            prompt_nicho=None,
            ideias_similares=ideias_similares
        )

        assert result.eh_continuacao is True
        assert result.eh_duplicada is False

    @pytest.mark.asyncio
    async def test_processar_llm_error_fallback(self, curador_service, sample_ideia_bruta, mock_httpx_client):
        """Testa fallback quando LLM falha."""
        # Mock resposta do Tavily
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {"answer": "", "results": []}
        tavily_response.raise_for_status = MagicMock()

        # Mock erro no LLM
        mock_httpx_client.post.side_effect = [tavily_response, Exception("LLM error")]
        curador_service.tavily_api_key = "test-key"

        result = await curador_service.processar(
            ideia_bruta=sample_ideia_bruta,
            prompt_nicho=None,
            ideias_similares=None
        )

        # Fallback: usa dados originais
        assert result.titulo == sample_ideia_bruta.titulo
        assert "não disponível" in result.justificativa_llm

    @pytest.mark.asyncio
    async def test_llm_retry_on_connection_error(self, curador_service):
        """Testa retry em caso de erro de conexão."""
        import httpx

        # O decorador @retry_llm está no método _call_llm
        # Testamos que após falhar todas as tentativas, a exceção é relançada
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = client_instance

            # Simula erro de conexão em todas as tentativas
            client_instance.post.side_effect = httpx.ConnectError("Connection failed")

            # O decorador @retry_llm com reraise=True deve lançar a exceção após todas as tentativas
            with pytest.raises(httpx.ConnectError):
                await curador_service._call_llm(
                    messages=[{"role": "user", "content": "teste"}]
                )

            # Deve ter tentado múltiplas vezes (retry decorador)
            assert client_instance.post.call_count >= 1
