"""
Agente Curador - Processa ideias brutas e as refina.

Fluxo:
1. Recebe ideia bruta (título/descrição)
2. Faz grounding via Tavily API para validar/enriquecer
3. Busca ideias similares no banco
4. Refina título/descrição usando o prompt do nicho
5. Retorna ideia estruturada com sinalização de duplicidade/continuação
"""
from dataclasses import dataclass
from typing import Any
import time

import httpx

from app.core.config import settings
from app.core.logging import curador_logger, AgentMetrics
from app.core.retry import retry_llm, retry_tavily
from app.services.embeddings import embedding_service


@dataclass
class IdeiaBruta:
    """Ideia crua recebida para curadoria."""
    titulo: str
    descricao: str | None = None
    nicho_id: str | None = None
    origem: str = "manual"


@dataclass
class IdeiaRefinada:
    """Ideia após processo de curadoria."""
    titulo: str
    descricao_breve: str
    eh_duplicada: bool = False
    eh_continuacao: bool = False
    ideia_similar_id: str | None = None
    ideia_similar_titulo: str | None = None
    similaridade: float | None = None
    contexto_grounding: str | None = None
    justificativa_llm: str | None = None


class CuradorService:
    """Serviço de curadoria de ideias via LiteLLM Proxy."""

    def __init__(self):
        self.litellm_base_url = settings.litellm_base_url
        self.litellm_api_key = settings.litellm_master_key or "dummy-key"
        self.tavily_api_key = settings.tavily_api_key
        self.llm_model = settings.llm_model
        self.similarity_threshold = settings.ideia_similarity_threshold

    @retry_llm()
    async def _call_llm(self, messages: list[dict], temperature: float = 0.7) -> str:
        """Faz chamada para o LLM via LiteLLM Proxy."""
        start_time = time.time()
        tokens_used = None

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.litellm_base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.litellm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.llm_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": 1000,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Extrai tokens usados (se disponível)
                usage = data.get("usage", {})
                tokens_used = usage.get("total_tokens")

                duration = time.time() - start_time
                curador_logger.log_llm_call(
                    model=self.llm_model,
                    tokens_used=tokens_used,
                    duration=round(duration, 3),
                    success=True
                )

                return data["choices"][0]["message"]["content"]

        except Exception as e:
            duration = time.time() - start_time
            curador_logger.log_llm_call(
                model=self.llm_model,
                tokens_used=tokens_used,
                duration=round(duration, 3),
                success=False,
                error=str(e)
            )
            raise

    @retry_tavily()
    async def _search_tavily(self, query: str, max_results: int = 5) -> str:
        """Busca informações via Tavily API para grounding."""
        if not self.tavily_api_key:
            return ""

        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers={
                        "Authorization": f"Bearer {self.tavily_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": query,
                        "max_results": max_results,
                        "include_answer": True,
                        "include_raw_content": False,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Extrai resposta e snippets relevantes
                parts = []
                if data.get("answer"):
                    parts.append(f"Resumo: {data['answer']}")

                if data.get("results"):
                    for r in data["results"][:3]:
                        parts.append(f"- {r.get('title', '')}: {r.get('content', '')[:200]}")

                duration = time.time() - start_time
                curador_logger.log_tavily_call(
                    query=query,
                    results_count=len(data.get("results", [])),
                    duration=round(duration, 3),
                    success=True
                )

                return "\n".join(parts) if parts else ""

        except Exception as e:
            duration = time.time() - start_time
            curador_logger.log_tavily_call(
                query=query,
                results_count=None,
                duration=round(duration, 3),
                success=False,
                error=str(e)
            )
            # Não propaga erro - grounding é opcional
            return ""

    async def processar(
        self,
        ideia_bruta: IdeiaBruta,
        prompt_nicho: str | None = None,
        ideias_similares: list[dict[str, Any]] | None = None,
    ) -> IdeiaRefinada:
        """
        Processa uma ideia bruta e retorna versão refinada.

        Args:
            ideia_bruta: Ideia crua com título e descrição opcional
            prompt_nicho: Prompt específico do nicho para refinamento
            ideias_similares: Lista de ideias similares encontradas (com id, titulo, similaridade)

        Returns:
            IdeiaRefinada com título e descrição refinados
        """
        # Inicia métricas
        metrics = curador_logger.start_operation(
            operation="processar_ideia",
            nicho_id=ideia_bruta.nicho_id
        )

        try:
            # 1. Grounding via Tavily (se API key configurada)
            contexto_grounding = ""
            query_tavily = f"{ideia_bruta.titulo}"
            if ideia_bruta.descricao:
                query_tavily += f" {ideia_bruta.descricao}"

            contexto_grounding = await self._search_tavily(query_tavily)
            grounding_used = bool(contexto_grounding)

            # 2. Analisa similaridade
            eh_duplicada = False
            eh_continuacao = False
            ideia_similar_id = None
            ideia_similar_titulo = None
            similaridade = None

            if ideias_similares:
                mais_similar = ideias_similares[0]
                similaridade = mais_similar.get("similaridade", 0)
                ideia_similar_id = mais_similar.get("id")
                ideia_similar_titulo = mais_similar.get("titulo")

                # Se similaridade > 0.95, consideramos duplicata
                if similaridade >= 0.95:
                    eh_duplicada = True
                # Se similaridade entre threshold e 0.95, pode ser continuação
                elif similaridade >= self.similarity_threshold:
                    eh_continuacao = True

                # Log da checagem de similaridade
                curador_logger.log_similarity_check(
                    similarity_score=similaridade,
                    is_duplicate=eh_duplicada,
                    is_continuation=eh_continuacao,
                    similar_ideia_id=ideia_similar_id
                )

            # 3. Monta prompt para refinamento
            sistema_prompt = """Você é um curador de ideias para vídeos. Sua função é refinar ideias brutas, tornando-as mais claras, atrativas e bem estruturadas para criadores de conteúdo.

Regras:
- Mantenha a essência da ideia original
- Melhore a clareza e o apelo do título
- Expanda a descrição com detalhes relevantes (máximo 2 frases)
- Se houver contexto de pesquisa, use-o para enriquecer a ideia
- Se houver ideias similares, considere se esta é uma continuação ou um tema relacionado
- Seja objetivo e direto

Responda APENAS no formato JSON:
{
  "titulo": "Título refinado (máximo 80 caracteres)",
  "descricao_breve": "Descrição breve (máximo 200 caracteres)",
  "justificativa": "Breve explicação das mudanças feitas"
}"""

            # Monta contexto do usuário
            usuario_parts = [f"Ideia original:\nTítulo: {ideia_bruta.titulo}"]
            if ideia_bruta.descricao:
                usuario_parts.append(f"Descrição: {ideia_bruta.descricao}")

            if contexto_grounding:
                usuario_parts.append(f"\nContexto de pesquisa:\n{contexto_grounding}")

            if ideias_similares:
                usuario_parts.append(f"\nIdeias similares encontradas:")
                for sim in ideias_similares[:3]:
                    usuario_parts.append(f"- '{sim['titulo']}' (similaridade: {sim['similaridade']:.2%})")

            if prompt_nicho:
                usuario_parts.append(f"\nPrompt do nicho: {prompt_nicho}")

            usuario_message = "\n".join(usuario_parts)

            # 4. Chama LLM para refinamento
            try:
                resposta_llm = await self._call_llm([
                    {"role": "system", "content": sistema_prompt},
                    {"role": "user", "content": usuario_message},
                ])

                # Parse da resposta JSON
                import json
                # Extrai JSON da resposta (pode vir com markdown)
                if "```json" in resposta_llm:
                    resposta_llm = resposta_llm.split("```json")[1].split("```")[0]
                elif "```" in resposta_llm:
                    resposta_llm = resposta_llm.split("```")[1].split("```")[0]

                dados_refinados = json.loads(resposta_llm.strip())
                titulo_refinado = dados_refinados.get("titulo", ideia_bruta.titulo)
                descricao_refinada = dados_refinados.get("descricao_breve", ideia_bruta.descricao or "")
                justificativa = dados_refinados.get("justificativa", "")

            except Exception as e:
                print(f"Erro no refinamento LLM: {e}")
                # Fallback: usa dados originais
                titulo_refinado = ideia_bruta.titulo
                descricao_refinada = ideia_bruta.descricao or ""
                justificativa = "Refinamento automático não disponível"

            resultado = IdeiaRefinada(
                titulo=titulo_refinado[:300],  # Limite do schema
                descricao_breve=descricao_refinada[:500],
                eh_duplicada=eh_duplicada,
                eh_continuacao=eh_continuacao,
                ideia_similar_id=ideia_similar_id,
                ideia_similar_titulo=ideia_similar_titulo,
                similaridade=similaridade,
                contexto_grounding=contexto_grounding if contexto_grounding else None,
                justificativa_llm=justificativa,
            )

            # Finaliza métricas
            curador_logger.end_operation(
                metrics=metrics,
                success=True,
                similarity_score=similaridade,
                is_duplicate=eh_duplicada,
                is_continuation=eh_continuacao,
                grounding_used=grounding_used
            )

            return resultado

        except Exception as e:
            # Finaliza métricas com erro
            curador_logger.end_operation(
                metrics=metrics,
                success=False,
                error=str(e)
            )
            raise


# Instância global do serviço
curador_service = CuradorService()
