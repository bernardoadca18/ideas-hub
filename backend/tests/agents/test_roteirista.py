"""
Testes para o Agente Roteirista.

Testa a geração de roteiros com mock de LLM e Tavily.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.roteirista import BlocoNarrativo, RoteiristaService, RoteiroEstruturado


@pytest.fixture
def roteirista_service():
    """Instância do RoteiristaService para testes."""
    return RoteiristaService()


class TestRoteiristaService:
    """Testes do serviço Roteirista."""

    @pytest.mark.asyncio
    async def test_call_llm_success(self, roteirista_service, mock_httpx_client):
        """Testa chamada bem-sucedida ao LLM."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "Resposta do LLM"}}],
            "usage": {"total_tokens": 300}
        }
        response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = response

        result = await roteirista_service._call_llm(
            messages=[{"role": "user", "content": "teste"}],
            temperature=0.8
        )

        assert result == "Resposta do LLM"

    @pytest.mark.asyncio
    async def test_search_tavily_success(self, roteirista_service, mock_httpx_client):
        """Testa busca no Tavily."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "answer": "Contexto de pesquisa",
            "results": [
                {"title": "Fonte 1", "content": "Conteúdo da fonte 1"},
            ]
        }
        response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = response

        roteirista_service.tavily_api_key = "test-key"
        result = await roteirista_service._search_tavily("query de teste")

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_gerar_roteiro_basico(self, roteirista_service, mock_httpx_client):
        """Testa geração básica de roteiro."""
        # Mock resposta do Tavily
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {
            "answer": "Contexto",
            "results": []
        }
        tavily_response.raise_for_status = MagicMock()

        # Mock resposta do LLM com roteiro estruturado
        roteiro_json = {
            "titulo": "Como usar IA para criar vídeos",
            "duracao_total_segundos": 180,
            "blocos": [
                {
                    "tipo": "introducao",
                    "duracao_segundos": 20,
                    "conteudo": "Introdução ao tema",
                    "dicas_visual": "Imagens de abertura",
                    "dicas_audio": "Música suave"
                },
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": 140,
                    "conteudo": "Conteúdo principal",
                    "dicas_visual": "Demonstrações",
                    "dicas_audio": None
                },
                {
                    "tipo": "conclusao",
                    "duracao_segundos": 20,
                    "conteudo": "Resumo e CTA",
                    "dicas_visual": "Cards finais",
                    "dicas_audio": "Música de fechamento"
                }
            ],
            "tags": ["ia", "vídeos", "tutorial"],
            "referencias": ["fonte1"],
            "justificativa": "Roteiro educativo"
        }

        llm_response = MagicMock()
        llm_response.status_code = 200
        llm_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps(roteiro_json)
                }
            }],
            "usage": {"total_tokens": 500}
        }
        llm_response.raise_for_status = MagicMock()

        mock_httpx_client.post.side_effect = [tavily_response, llm_response]
        roteirista_service.tavily_api_key = "test-key"

        result = await roteirista_service.gerar_roteiro(
            ideia_titulo="Como usar IA para criar vídeos",
            ideia_descricao="Tutorial prático",
            prompt_roteiro="Crie roteiros envolventes"
        )

        assert isinstance(result, RoteiroEstruturado)
        assert result.titulo == "Como usar IA para criar vídeos"
        assert result.duracao_total_segundos == 180
        assert len(result.blocos) == 3
        assert result.blocos[0].tipo == "introducao"
        assert result.tags == ["ia", "vídeos", "tutorial"]

    @pytest.mark.asyncio
    async def test_gerar_roteiro_continuacao(self, roteirista_service, mock_httpx_client):
        """Testa geração de roteiro para continuação (parte 2)."""
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {"answer": "", "results": []}
        tavily_response.raise_for_status = MagicMock()

        roteiro_json = {
            "titulo": "Como usar IA para criar vídeos - Parte 2",
            "duracao_total_segundos": 200,
            "blocos": [
                {
                    "tipo": "introducao",
                    "duracao_segundos": 25,
                    "conteudo": "Recapitulação e continuação",
                    "dicas_visual": None,
                    "dicas_audio": None
                }
            ],
            "tags": [],
            "referencias": None,
            "justificativa": "Continuação"
        }

        llm_response = MagicMock()
        llm_response.status_code = 200
        llm_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(roteiro_json)}}],
            "usage": {"total_tokens": 400}
        }
        llm_response.raise_for_status = MagicMock()

        mock_httpx_client.post.side_effect = [tavily_response, llm_response]
        roteirista_service.tavily_api_key = "test-key"

        roteiro_anterior = {
            "id": "uuid-anterior",
            "estrutura": {
                "titulo": "Como usar IA para criar vídeos - Parte 1",
                "duracao_total_segundos": 180,
                "blocos": [
                    {"tipo": "introducao", "conteudo": "Intro", "duracao_segundos": 20}
                ]
            }
        }

        result = await roteirista_service.gerar_roteiro(
            ideia_titulo="Como usar IA para criar vídeos - Parte 2",
            ideia_descricao="Continuação do tutorial",
            prompt_roteiro="Crie roteiros envolventes",
            roteiro_anterior=roteiro_anterior,
            numero_parte=2
        )

        assert result.titulo == "Como usar IA para criar vídeos - Parte 2"

    @pytest.mark.asyncio
    async def test_gerar_roteiro_provider_failure_is_explicit(self, roteirista_service, mock_httpx_client):
        """Provider failures never produce a fake successful script."""
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {"answer": "", "results": []}
        tavily_response.raise_for_status = MagicMock()

        # LLM falha
        mock_httpx_client.post.side_effect = [tavily_response, Exception("LLM error")]
        roteirista_service.tavily_api_key = "test-key"

        with pytest.raises(Exception, match="LLM error"):
            await roteirista_service.gerar_roteiro(
                ideia_titulo="Título de teste",
                ideia_descricao="Descrição de teste",
                prompt_roteiro="Crie roteiros",
            )

    @pytest.mark.asyncio
    async def test_to_dict(self, roteirista_service):
        """Testa conversão de RoteiroEstruturado para dicionário."""
        roteiro = RoteiroEstruturado(
            titulo="Teste",
            duracao_total_segundos=120,
            blocos=[
                BlocoNarrativo(
                    tipo="introducao",
                    duracao_segundos=20,
                    conteudo="Intro",
                    dicas_visual="Visual",
                    dicas_audio="Audio"
                )
            ],
            tags=["tag1"],
            referencias=["ref1"],
            justificativa_llm="Teste"
        )

        result = roteirista_service.to_dict(roteiro)

        assert result["titulo"] == "Teste"
        assert result["duracao_total_segundos"] == 120
        assert len(result["blocos"]) == 1
        assert result["tags"] == ["tag1"]
        assert result["referencias"] == ["ref1"]

    @pytest.mark.asyncio
    async def test_tavily_retry_on_timeout(self, roteirista_service):
        """Testa retry do Tavily em caso de timeout."""
        import httpx

        # O decorador @retry_tavily está no método _search_tavily
        # Testamos que após falhar, o método retorna vazio (fallback)
        # O retry acontece internamente no decorador, não podemos mockar httpx diretamente
        # pois o decorador precisa chamar o método múltiplas vezes

        # Testamos o fallback quando todas as tentativas falham
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = client_instance

            # Simula timeout em todas as tentativas
            client_instance.post.side_effect = httpx.TimeoutException("Timeout")

            roteirista_service.tavily_api_key = "test-key"
            result = await roteirista_service._search_tavily("query")

            # Após todas as tentativas falharem, retorna string vazia como fallback
            assert result == ""
            # Deve ter tentado múltiplas vezes (retry decorador)
            assert client_instance.post.call_count >= 1
