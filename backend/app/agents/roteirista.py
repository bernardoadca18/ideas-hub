"""
Agente Roteirista - Gera roteiros estruturados a partir de ideias aprovadas.

Fluxo:
1. Recebe ideia aprovada + nicho (prompt_roteiro)
2. Se parte 2+, busca roteiro anterior como contexto
3. Faz grounding via Tavily API
4. Gera estrutura em blocos narrativos
5. Retorna roteiro estruturado para revisão
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID
import time

import httpx

from app.core.config import settings
from app.core.logging import roteirista_logger
from app.core.retry import retry_llm, retry_tavily


@dataclass
class BlocoNarrativo:
    """Bloco narrativo do roteiro."""
    tipo: str  # introducao, desenvolvimento, conclusao, etc.
    duracao_segundos: int
    conteudo: str
    dicas_visual: str | None = None
    dicas_audio: str | None = None


@dataclass
class RoteiroEstruturado:
    """Roteiro completo com estrutura em blocos."""
    titulo: str
    duracao_total_segundos: int
    blocos: list[BlocoNarrativo]
    tags: list[str]
    referencias: list[str] | None = None
    justificativa_llm: str | None = None


class RoteiristaService:
    """Serviço de geração de roteiros via LiteLLM Proxy."""

    def __init__(self):
        self.litellm_base_url = settings.litellm_base_url
        self.litellm_api_key = settings.litellm_master_key or "dummy-key"
        self.tavily_api_key = settings.tavily_api_key
        self.llm_model = settings.llm_model

    @retry_llm()
    async def _call_llm(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 3000) -> str:
        """Faz chamada para o LLM via LiteLLM Proxy."""
        start_time = time.time()
        tokens_used = None

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
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
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Extrai tokens usados (se disponível)
                usage = data.get("usage", {})
                tokens_used = usage.get("total_tokens")

                duration = time.time() - start_time
                roteirista_logger.log_llm_call(
                    model=self.llm_model,
                    tokens_used=tokens_used,
                    duration=round(duration, 3),
                    success=True
                )

                return data["choices"][0]["message"]["content"]

        except Exception as e:
            duration = time.time() - start_time
            roteirista_logger.log_llm_call(
                model=self.llm_model,
                tokens_used=tokens_used,
                duration=round(duration, 3),
                success=False,
                error=str(e)
            )
            raise

    @retry_tavily()
    async def _search_tavily(self, query: str, max_results: int = 7) -> str:
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
                    for r in data["results"][:5]:
                        parts.append(f"- {r.get('title', '')}: {r.get('content', '')[:300]}")

                duration = time.time() - start_time
                roteirista_logger.log_tavily_call(
                    query=query,
                    results_count=len(data.get("results", [])),
                    duration=round(duration, 3),
                    success=True
                )

                return "\n".join(parts) if parts else ""

        except Exception as e:
            duration = time.time() - start_time
            roteirista_logger.log_tavily_call(
                query=query,
                results_count=None,
                duration=round(duration, 3),
                success=False,
                error=str(e)
            )
            # Não propaga erro - grounding é opcional
            return ""

    async def gerar_roteiro(
        self,
        ideia_titulo: str,
        ideia_descricao: str | None,
        prompt_roteiro: str,
        roteiro_anterior: dict | None = None,
        numero_parte: int | None = None,
        ideia_id: str | None = None,
    ) -> RoteiroEstruturado:
        """
        Gera um roteiro estruturado a partir de uma ideia.

        Args:
            ideia_titulo: Título da ideia
            ideia_descricao: Descrição da ideia
            prompt_roteiro: Prompt específico do nicho para roteiros
            roteiro_anterior: Roteiro da parte anterior (se continuação)
            numero_parte: Número da parte (se continuação)
            ideia_id: ID da ideia (para logging)

        Returns:
            RoteiroEstruturado com blocos narrativos
        """
        # Inicia métricas
        metrics = roteirista_logger.start_operation(
            operation="gerar_roteiro",
            ideia_id=ideia_id
        )

        try:
            # 1. Grounding via Tavily
            query_tavily = ideia_titulo
            if ideia_descricao:
                query_tavily += f" {ideia_descricao}"

            contexto_grounding = await self._search_tavily(query_tavily)

            # 2. Monta prompt do sistema
            sistema_prompt = """Você é um roteirista profissional de vídeos para YouTube e redes sociais. Sua função é criar roteiros estruturados, práticos e envolventes.

Regras de estrutura:
- Divida o roteiro em blocos narrativos lógicos
- Cada bloco deve ter duração estimada em segundos
- Inclua dicas visuais e de áudio para cada bloco
- Mantenha o ritmo dinâmico e a atenção do espectador
- Use técnicas de storytelling (gancho, conflito, resolução)

Blocos sugeridos:
1. introducao (15-30s): Gancho inicial, apresentação do tema
2. desenvolvimento (60-180s): Conteúdo principal, pode ter múltiplos blocos
3. conclusao (15-30s): Resumo, call-to-action

Para continuações (parte 2+):
- Inicie com recapitulação breve
- Mantenha consistência com o tom e estilo anteriores
- Referencie pontos da parte anterior quando relevante

Responda APENAS no formato JSON:
{
  "titulo": "Título do vídeo (máximo 80 caracteres)",
  "duracao_total_segundos": 180,
  "blocos": [
    {
      "tipo": "introducao",
      "duracao_segundos": 20,
      "conteudo": "Texto do que será falado/apresentado",
      "dicas_visual": "Sugestões de imagens, vídeos, gráficos",
      "dicas_audio": "Sugestões de música, efeitos sonoros"
    }
  ],
  "tags": ["tag1", "tag2", "tag3"],
  "referencias": ["fonte1", "fonte2"],
  "justificativa": "Breve explicação das escolhas criativas"
}"""

            # 3. Monta contexto do usuário
            usuario_parts = [f"Ideia do vídeo:\nTítulo: {ideia_titulo}"]
            if ideia_descricao:
                usuario_parts.append(f"Descrição: {ideia_descricao}")

            usuario_parts.append(f"\nPrompt do nicho: {prompt_roteiro}")

            if contexto_grounding:
                usuario_parts.append(f"\nContexto de pesquisa:\n{contexto_grounding}")

            if roteiro_anterior and numero_parte:
                usuario_parts.append(f"\n=== ESTA É A PARTE {numero_parte} ===")
                usuario_parts.append(f"\nRoteiro da parte {numero_parte - 1}:")
                # Extrai estrutura do roteiro anterior
                estrutura_ant = roteiro_anterior.get("estrutura", {})
                blocos_ant = estrutura_ant.get("blocos", [])
                if blocos_ant:
                    usuario_parts.append(f"Título anterior: {estrutura_ant.get('titulo', 'N/A')}")
                    usuario_parts.append(f"Duração anterior: {estrutura_ant.get('duracao_total_segundos', 'N/A')}s")
                    usuario_parts.append(f"Número de blocos anteriores: {len(blocos_ant)}")
                    # Resumo dos últimos blocos
                    if len(blocos_ant) > 0:
                        ultimo_bloco = blocos_ant[-1]
                        usuario_parts.append(f"Último bloco anterior: {ultimo_bloco.get('conteudo', '')[:150]}...")

            usuario_message = "\n".join(usuario_parts)

            # 4. Chama LLM para gerar roteiro
            try:
                resposta_llm = await self._call_llm(
                    messages=[
                        {"role": "system", "content": sistema_prompt},
                        {"role": "user", "content": usuario_message},
                    ],
                    temperature=0.8,  # Mais criatividade para roteiros
                )

                # Parse da resposta JSON
                import json
                # Extrai JSON da resposta (pode vir com markdown)
                if "```json" in resposta_llm:
                    resposta_llm = resposta_llm.split("```json")[1].split("```")[0]
                elif "```" in resposta_llm:
                    resposta_llm = resposta_llm.split("```")[1].split("```")[0]

                dados = json.loads(resposta_llm.strip())

                # Converte para estrutura de dados
                blocos = []
                for b in dados.get("blocos", []):
                    blocos.append(BlocoNarrativo(
                        tipo=b.get("tipo", "desenvolvimento"),
                        duracao_segundos=b.get("duracao_segundos", 60),
                        conteudo=b.get("conteudo", ""),
                        dicas_visual=b.get("dicas_visual"),
                        dicas_audio=b.get("dicas_audio"),
                    ))

                resultado = RoteiroEstruturado(
                    titulo=dados.get("titulo", ideia_titulo)[:80],
                    duracao_total_segundos=dados.get("duracao_total_segundos", 180),
                    blocos=blocos,
                    tags=dados.get("tags", []),
                    referencias=dados.get("referencias"),
                    justificativa_llm=dados.get("justificativa"),
                )

                # Finaliza métricas
                roteirista_logger.end_operation(
                    metrics=metrics,
                    success=True,
                    num_blocos=len(blocos),
                    duracao_total_segundos=resultado.duracao_total_segundos
                )

                return resultado

            except Exception as e:
                print(f"Erro na geração do roteiro: {e}")
                # Fallback: cria roteiro básico
                resultado = RoteiroEstruturado(
                    titulo=ideia_titulo[:80],
                    duracao_total_segundos=120,
                    blocos=[
                        BlocoNarrativo(
                            tipo="introducao",
                            duracao_segundos=20,
                            conteudo=f"Apresentação do tema: {ideia_titulo}",
                            dicas_visual="Imagens de abertura",
                            dicas_audio="Música de fundo leve",
                        ),
                        BlocoNarrativo(
                            tipo="desenvolvimento",
                            duracao_segundos=80,
                            conteudo=ideia_descricao or f"Desenvolvimento do tema: {ideia_titulo}",
                            dicas_visual="B-roll relacionado ao tema",
                            dicas_audio=None,
                        ),
                        BlocoNarrativo(
                            tipo="conclusao",
                            duracao_segundos=20,
                            conteudo="Resumo e call-to-action",
                            dicas_visual="Cards finais",
                            dicas_audio="Música de fechamento",
                        ),
                    ],
                    tags=[],
                    referencias=None,
                    justificativa_llm="Roteiro gerado automaticamente (fallback)",
                )

                # Finaliza métricas (fallback ainda é sucesso)
                roteirista_logger.end_operation(
                    metrics=metrics,
                    success=True,
                    num_blocos=3,
                    duracao_total_segundos=120,
                    error=f"Usou fallback: {str(e)}"
                )

                return resultado

        except Exception as e:
            # Finaliza métricas com erro
            roteirista_logger.end_operation(
                metrics=metrics,
                success=False,
                error=str(e)
            )
            raise

    def to_dict(self, roteiro: RoteiroEstruturado) -> dict:
        """Converte RoteiroEstruturado para dicionário (JSON)."""
        return {
            "titulo": roteiro.titulo,
            "duracao_total_segundos": roteiro.duracao_total_segundos,
            "blocos": [
                {
                    "tipo": b.tipo,
                    "duracao_segundos": b.duracao_segundos,
                    "conteudo": b.conteudo,
                    "dicas_visual": b.dicas_visual,
                    "dicas_audio": b.dicas_audio,
                }
                for b in roteiro.blocos
            ],
            "tags": roteiro.tags,
            "referencias": roteiro.referencias,
            "justificativa_llm": roteiro.justificativa_llm,
        }


# Instância global do serviço
roteirista_service = RoteiristaService()
