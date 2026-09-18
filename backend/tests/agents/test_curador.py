"""
Testes para o Agente Curador.

Testa o processamento de ideias com mock de LLM e Tavily.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agents.curador import CuradorService, IdeiaRefinada


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
            "usage": {"total_tokens": 150},
        }
        response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = response

        result = await curador_service._call_llm(
            messages=[{"role": "user", "content": "teste"}], temperature=0.7
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
            ],
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
    async def test_processar_ideia_bruta(
        self, curador_service, sample_ideia_bruta, mock_httpx_client
    ):
        """Testa processamento completo de ideia bruta."""
        # Mock resposta do Tavily
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {
            "answer": "Contexto de pesquisa",
            "results": [],
        }
        tavily_response.raise_for_status = MagicMock()

        # Mock resposta do LLM
        llm_response = MagicMock()
        llm_response.status_code = 200
        llm_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "titulo": "Título refinado",
                                "descricao_breve": "Descrição refinada",
                                "justificativa": "Teste",
                            }
                        )
                    }
                }
            ],
            "usage": {"total_tokens": 200},
        }
        llm_response.raise_for_status = MagicMock()

        mock_httpx_client.post.side_effect = [tavily_response, llm_response]
        curador_service.tavily_api_key = "test-key"

        result = await curador_service.processar(
            ideia_bruta=sample_ideia_bruta,
            prompt_nicho="Crie ideias sobre tecnologia",
            ideias_similares=None,
        )

        assert isinstance(result, IdeiaRefinada)
        assert result.titulo == "Título refinado"
        assert result.descricao_breve == "Descrição refinada"
        assert result.eh_duplicada is False

    @pytest.mark.asyncio
    async def test_processar_ideia_duplicada(
        self, curador_service, sample_ideia_bruta, mock_httpx_client
    ):
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
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "titulo": "Título refinado",
                                "descricao_breve": "Descrição refinada",
                                "justificativa": "Teste",
                            }
                        )
                    }
                }
            ],
            "usage": {"total_tokens": 200},
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
            ideias_similares=ideias_similares,
        )

        assert result.eh_duplicada is True
        assert result.similaridade == 0.96

    @pytest.mark.asyncio
    async def test_processar_ideia_continuacao(
        self, curador_service, sample_ideia_bruta, mock_httpx_client
    ):
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
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "titulo": "Título refinado",
                                "descricao_breve": "Descrição refinada",
                                "justificativa": "Teste",
                            }
                        )
                    }
                }
            ],
            "usage": {"total_tokens": 200},
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
            ideias_similares=ideias_similares,
        )

        assert result.eh_continuacao is True
        assert result.eh_duplicada is False

    @pytest.mark.asyncio
    async def test_processar_llm_error_is_explicit(
        self, curador_service, sample_ideia_bruta, mock_httpx_client
    ):
        """Provider failure must not be converted into a successful refinement."""
        # Mock resposta do Tavily
        tavily_response = MagicMock()
        tavily_response.status_code = 200
        tavily_response.json.return_value = {"answer": "", "results": []}
        tavily_response.raise_for_status = MagicMock()

        # Mock erro no LLM
        mock_httpx_client.post.side_effect = [tavily_response, Exception("LLM error")]
        curador_service.tavily_api_key = "test-key"

        with pytest.raises(Exception, match="LLM error"):
            await curador_service.processar(
                ideia_bruta=sample_ideia_bruta,
                prompt_nicho=None,
                ideias_similares=None,
            )

    @pytest.mark.parametrize(
        ("score", "duplicate", "continuation"),
        [(0.97, True, False), (0.90, False, True), (0.84, False, False)],
    )
    @pytest.mark.asyncio
    async def test_similarity_boundaries_use_real_score(
        self, curador_service, sample_ideia_bruta, score, duplicate, continuation
    ):
        curador_service.tavily_api_key = None
        curador_service._call_llm = AsyncMock(
            return_value=json.dumps(
                {
                    "titulo": "Refinada",
                    "descricao_breve": "Descrição",
                    "justificativa": "ok",
                }
            )
        )
        result = await curador_service.processar(
            sample_ideia_bruta,
            ideias_similares=[{"id": "id", "titulo": "Similar", "similaridade": score}],
        )
        assert result.similaridade == score
        assert result.eh_duplicada is duplicate
        assert result.eh_continuacao is continuation

    @pytest.mark.asyncio
    async def test_llm_retry_on_connection_error(self, curador_service):
        """Testa retry em caso de erro de conexão."""
        import httpx
        from app.services.llm_gateway import LLMFailureCategory, LLMGatewayError

        # The shared gateway classifies the exhausted transport failure.
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value = client_instance
            mock_client.return_value.__aenter__.return_value = client_instance

            # Simula erro de conexão em todas as tentativas
            client_instance.post.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(LLMGatewayError) as captured:
                await curador_service._call_llm(
                    messages=[{"role": "user", "content": "teste"}]
                )

            assert captured.value.category is LLMFailureCategory.TRANSPORT
            assert client_instance.post.call_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["pt-BR", "en-US"])
async def test_refinement_sends_schema_to_gateway(curador_service, locale):
    from types import SimpleNamespace

    from app.agents.curador import IdeiaBruta
    from app.prompts.editorial_v3 import spoken_language_policy
    from app.schemas.llm_outputs import IdeaRefinementOutput
    from app.services.llm_gateway import LLMTaskRole

    output = {
        "titulo": "Refined idea" if locale == "en-US" else "Ideia refinada",
        "descricao_breve": "Description" if locale == "en-US" else "Descrição",
        "justificativa": "Grounded angle",
    }
    curador_service._search_tavily = AsyncMock(return_value="")
    result = SimpleNamespace(
        content=json.dumps(output), model_alias="test", total_tokens=10, latency_seconds=0.1
    )
    with patch("app.agents.curador.llm_gateway.complete", AsyncMock(return_value=result)) as complete:
        refined = await curador_service.processar(
            IdeiaBruta(titulo="Source idea"), content_locale=locale
        )
    assert refined.titulo == output["titulo"]
    assert refined.descricao_breve == output["descricao_breve"]
    complete.assert_awaited_once()
    kwargs = complete.call_args.kwargs
    assert kwargs["response_schema"] == IdeaRefinementOutput.model_json_schema()
    assert kwargs["role"] is LLMTaskRole.FAST
    assert kwargs["temperature"] == 0.7 and kwargs["max_tokens"] == 1000
    assert (spoken_language_policy("en-US") in kwargs["messages"][0]["content"]) == (locale == "en-US")


@pytest.mark.asyncio
async def test_raw_idea_sends_schema_to_gateway(curador_service):
    from types import SimpleNamespace

    from app.schemas.llm_outputs import RawIdeaOutput
    from app.services.llm_gateway import LLMTaskRole

    result = SimpleNamespace(
        content=json.dumps({"titulo": "Ideia bruta", "descricao": "Descrição"}),
        model_alias="test", total_tokens=10, latency_seconds=0.1,
    )
    with patch("app.agents.curador.llm_gateway.complete", AsyncMock(return_value=result)) as complete:
        raw = await curador_service.gerar_ideia_bruta("trend", None, None, 1, 1)
    assert raw.titulo == "Ideia bruta" and raw.descricao == "Descrição"
    complete.assert_awaited_once()
    kwargs = complete.call_args.kwargs
    assert kwargs["response_schema"] == RawIdeaOutput.model_json_schema()
    assert kwargs["role"] is LLMTaskRole.FAST
    assert kwargs["temperature"] == 0.8 and kwargs["max_tokens"] == 1000
