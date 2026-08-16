"""
Agente Roteirista - Gera roteiros estruturados a partir de ideias aprovadas.

Fluxo:
1. Recebe ideia aprovada + nicho + perfil de produção
2. Se parte 2+, busca roteiro anterior como contexto
3. Faz grounding via Tavily API (se o perfil permitir)
4. Compõe o prompt via PromptBuilder (base + qualidade editorial + perfil + nicho + workflow)
5. Gera estrutura em blocos narrativos
6. Retorna roteiro estruturado para revisão
"""
from dataclasses import dataclass
from typing import Any
import time

import httpx

from app.core.config import settings
from app.core.logging import roteirista_logger
from app.core.retry import retry_llm, retry_tavily
from app.production_profiles import ProductionProfile, get_profile
from app.prompts.builder import PromptBuilder
from app.prompts.workflows import get_workflow, ROTEIRO_PADRAO


@dataclass
class BlocoNarrativo:
    """Bloco narrativo do roteiro."""
    tipo: str  # rótulo descritivo do papel do bloco (varia por perfil/assunto)
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
    prompt_trace: dict | None = None  # observabilidade: perfil/workflow/componentes usados


class RoteiristaService:
    """Serviço de geração de roteiros via LiteLLM Proxy."""

    # Piso técnico absoluto só para evitar um roteiro de poucos segundos em caso de
    # resposta degenerada do modelo. Não é a "duração-alvo" (isso é responsabilidade
    # do ProductionProfile) — é só uma rede de segurança.
    _PISO_TECNICO_SEGUNDOS = 60

    def __init__(self):
        self.litellm_base_url = settings.litellm_base_url
        self.litellm_api_key = settings.litellm_master_key or "dummy-key"
        self.tavily_api_key = settings.tavily_api_key
        self.llm_model = settings.llm_model

    @retry_llm()
    async def _call_llm(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 8000) -> str:
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
            return ""

    async def gerar_roteiro(
        self,
        ideia_titulo: str,
        ideia_descricao: str | None,
        prompt_roteiro: str | None,
        roteiro_anterior: dict | None = None,
        numero_parte: int | None = None,
        ideia_id: str | None = None,
        perfil_id: str | None = None,
        workflow_id: str | None = None,
    ) -> RoteiroEstruturado:
        """
        Gera um roteiro estruturado a partir de uma ideia.

        Args:
            ideia_titulo: Título da ideia
            ideia_descricao: Descrição da ideia
            prompt_roteiro: Prompt específico do nicho (texto livre, camada NicheContext)
            roteiro_anterior: Roteiro da parte anterior (se continuação)
            numero_parte: Número da parte (se continuação)
            ideia_id: ID da ideia (para logging)
            perfil_id: id do ProductionProfile ativo (resolvido a partir do Nicho)
            workflow_id: override explícito do workflow (default: profile.workflow_roteiro)

        Returns:
            RoteiroEstruturado com blocos narrativos
        """
        metrics = roteirista_logger.start_operation(operation="gerar_roteiro", ideia_id=ideia_id)

        try:
            profile: ProductionProfile = get_profile(perfil_id)
            workflow = get_workflow(workflow_id or profile.workflow_roteiro)

            contexto_grounding = ""
            if profile.permite_grounding_automatico:
                query_tavily = ideia_titulo
                if ideia_descricao:
                    query_tavily += f" {ideia_descricao}"
                contexto_grounding = await self._search_tavily(query_tavily)

            usuario_parts = [f"Ideia do vídeo:\nTítulo: {ideia_titulo}"]
            if ideia_descricao:
                usuario_parts.append(f"Descrição: {ideia_descricao}")

            if roteiro_anterior and numero_parte:
                usuario_parts.append(f"\n=== ESTA É A PARTE {numero_parte} ===")
                estrutura_ant = roteiro_anterior.get("estrutura", {})
                blocos_ant = estrutura_ant.get("blocos", [])
                if blocos_ant:
                    usuario_parts.append(f"Título anterior: {estrutura_ant.get('titulo', 'N/A')}")
                    usuario_parts.append(f"Duração anterior: {estrutura_ant.get('duracao_total_segundos', 'N/A')}s")
                    usuario_parts.append(f"Número de blocos anteriores: {len(blocos_ant)}")
                    ultimo_bloco = blocos_ant[-1]
                    usuario_parts.append(f"Último bloco anterior: {ultimo_bloco.get('conteudo', '')[:150]}...")

            usuario_message = "\n".join(usuario_parts)

            composed = (
                PromptBuilder(workflow=workflow, profile=profile)
                .with_niche(prompt_roteiro)
                .with_grounding(contexto_grounding)
                .build(task_context=usuario_message)
            )

            try:
                resposta_llm = await self._call_llm(
                    messages=[
                        {"role": "system", "content": composed.system},
                        {"role": "user", "content": composed.user},
                    ],
                    temperature=0.8,
                )

                import json
                if "```json" in resposta_llm:
                    resposta_llm = resposta_llm.split("```json")[1].split("```")[0]
                elif "```" in resposta_llm:
                    resposta_llm = resposta_llm.split("```")[1].split("```")[0]

                dados = json.loads(resposta_llm.strip())

                blocos = []
                duracao_total_calculada = 0
                for b in dados.get("blocos", []):
                    duracao_bloco = b.get("duracao_segundos", 60)
                    blocos.append(BlocoNarrativo(
                        tipo=b.get("tipo", "desenvolvimento"),
                        duracao_segundos=duracao_bloco,
                        conteudo=b.get("conteudo", ""),
                        dicas_visual=b.get("dicas_visual"),
                        dicas_audio=b.get("dicas_audio"),
                    ))
                    duracao_total_calculada += duracao_bloco

                # Duração final: o que o modelo produziu de fato, respeitando só um piso
                # técnico de segurança — NUNCA um mínimo editorial artificial por perfil.
                duracao_final = max(
                    dados.get("duracao_total_segundos", duracao_total_calculada),
                    duracao_total_calculada,
                    self._PISO_TECNICO_SEGUNDOS,
                )

                resultado = RoteiroEstruturado(
                    titulo=dados.get("titulo", ideia_titulo)[:80],
                    duracao_total_segundos=duracao_final,
                    blocos=blocos,
                    tags=dados.get("tags", []),
                    referencias=dados.get("referencias"),
                    justificativa_llm=dados.get("justificativa"),
                    prompt_trace=composed.trace,
                )

                # Validar duração contra política do perfil
                duracao_policy = profile.duracao
                target_min = duracao_policy.target_min_seconds
                target_max = duracao_policy.target_max_seconds

                dentro_do_esperado = True
                warning_msg = None
                if target_min is not None and duracao_final < target_min:
                    dentro_do_esperado = False
                    warning_msg = (
                        f"Roteiro gerado com {duracao_final}s, abaixo do mínimo esperado ({target_min}s) "
                        f"para o perfil '{profile.id}'. Verifique se o conteúdo de entrada é suficiente."
                    )
                    print(f"[WARNING] {warning_msg}")
                elif target_max is not None and duracao_final > target_max and not duracao_policy.allow_extended:
                    dentro_do_esperado = False
                    warning_msg = (
                        f"Roteiro gerado com {duracao_final}s, acima do máximo ({target_max}s) "
                        f"para o perfil '{profile.id}'."
                    )

                roteirista_logger.log_duration_check(
                    duracao_gerada=duracao_final,
                    target_min=target_min,
                    target_max=target_max,
                    profile_id=profile.id,
                    dentro_do_esperado=dentro_do_esperado,
                    warning=warning_msg
                )

                roteirista_logger.end_operation(
                    metrics=metrics, success=True, num_blocos=len(blocos),
                    duracao_total_segundos=resultado.duracao_total_segundos,
                )

                return resultado

            except Exception as e:
                import traceback
                print(f"Erro na geração do roteiro: {e}")
                print(traceback.format_exc())

                roteirista_logger.log_llm_call(
                    model=self.llm_model, tokens_used=None, duration=0, success=False,
                    error=f"Fallback acionado: {str(e)}",
                )

                # Fallback minimalista e claramente sinalizado como tal (não é um roteiro
                # "de verdade" — é só para o pipeline não travar). Não tenta simular a
                # estrutura ideal, porque isso reforçaria a mesma fórmula genérica que
                # queremos evitar quando o LLM de fato responde.
                resultado = RoteiroEstruturado(
                    titulo=ideia_titulo[:80],
                    duracao_total_segundos=self._PISO_TECNICO_SEGUNDOS,
                    blocos=[
                        BlocoNarrativo(
                            tipo="fallback_erro",
                            duracao_segundos=self._PISO_TECNICO_SEGUNDOS,
                            conteudo=(
                                f"[FALLBACK] Geração automática falhou para a ideia '{ideia_titulo}'. "
                                f"Regenere manualmente. Erro original: {str(e)}"
                            ),
                            dicas_visual=None,
                            dicas_audio=None,
                        ),
                    ],
                    tags=[],
                    referencias=None,
                    justificativa_llm=f"Roteiro de fallback — geração via LLM falhou: {str(e)}",
                    prompt_trace=composed.trace,
                )

                roteirista_logger.end_operation(
                    metrics=metrics, success=True, num_blocos=1,
                    duracao_total_segundos=resultado.duracao_total_segundos,
                    error=f"Usou fallback: {str(e)}",
                )

                return resultado

        except Exception as e:
            roteirista_logger.end_operation(metrics=metrics, success=False, error=str(e))
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
            "prompt_trace": roteiro.prompt_trace,
        }


roteirista_service = RoteiristaService()
