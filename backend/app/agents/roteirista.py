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

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import roteirista_logger
from app.core.retry import retry_tavily
from app.production_profiles import ProductionProfile, get_profile
from app.prompts.builder import PromptBuilder
from app.prompts.workflows import get_workflow
from app.schemas.llm_outputs import ScriptLLMOutput, validate_model_output
from app.schemas.visual_query import VisualQuery
from app.services.llm_gateway import LLMTaskRole, llm_gateway


@dataclass
class BlocoNarrativo:
    """Bloco narrativo do roteiro."""

    tipo: str  # rótulo descritivo do papel do bloco (varia por perfil/assunto)
    duracao_segundos: int
    conteudo: str
    dicas_visual: str | None = None
    dicas_audio: str | None = None
    visual_queries: list[VisualQuery] = field(default_factory=list)
    purpose: str | None = None
    beats: list[dict[str, Any]] = field(default_factory=list)
    planned_beats: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    audio_intent: dict[str, Any] | None = None
    # Explicit editorial display text.  This is deliberately distinct from
    # ``tipo``, which remains a structural/category label for legacy scripts.
    display_title: str | None = None


@dataclass
class RoteiroEstruturado:
    """Roteiro completo com estrutura em blocos."""

    titulo: str
    duracao_total_segundos: int
    blocos: list[BlocoNarrativo]
    tags: list[str]
    referencias: list[str] | None = None
    justificativa_llm: str | None = None
    prompt_trace: dict | None = (
        None  # observabilidade: perfil/workflow/componentes usados
    )
    media_context: dict[str, Any] | None = None
    duration_contract: dict[str, Any] | None = None
    editorial_quality: dict[str, Any] | None = None


class RoteiristaService:
    """Gerador legado isolado atrás do gateway provider-neutral."""

    # Piso técnico absoluto só para evitar um roteiro de poucos segundos em caso de
    # resposta degenerada do modelo. Não é a "duração-alvo" (isso é responsabilidade
    # do ProductionProfile) — é só uma rede de segurança.
    _PISO_TECNICO_SEGUNDOS = 60

    def __init__(self):
        self.tavily_api_key = settings.tavily_api_key

    async def _call_llm(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 8000,
        *,
        role: LLMTaskRole = LLMTaskRole.WRITING,
        prompt_identity: str | None = None,
    ) -> str:
        """Faz chamada para o LLM pelo gateway compartilhado."""
        result = await llm_gateway.complete(
            messages=messages,
            role=role,
            temperature=temperature,
            max_tokens=max_tokens,
            prompt_identity=prompt_identity,
            response_schema=ScriptLLMOutput.model_json_schema(),
        )
        roteirista_logger.log_llm_call(
            model=result.model_alias,
            tokens_used=result.total_tokens,
            duration=result.latency_seconds,
            success=True,
        )
        return result.content

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
                        parts.append(
                            f"- {r.get('title', '')}: {r.get('content', '')[:300]}"
                        )

                duration = time.time() - start_time
                roteirista_logger.log_tavily_call(
                    query=query,
                    results_count=len(data.get("results", [])),
                    duration=round(duration, 3),
                    success=True,
                )

                return "\n".join(parts) if parts else ""

        except Exception as e:  # noqa: BLE001 - optional external-grounding boundary
            duration = time.time() - start_time
            roteirista_logger.log_tavily_call(
                query=query,
                results_count=None,
                duration=round(duration, 3),
                success=False,
                error=str(e),
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
        author_briefing: str | None = None,
        revision_source: dict[str, Any] | None = None,
        revision_feedback: str | None = None,
        duration_contract_prompt: str | None = None,
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
            author_briefing: intenção/opinião editorial fornecida pelo autor
            revision_source: estrutura imutável da versão anterior, em regenerações
            revision_feedback: feedback explícito do operador para a nova versão

        Returns:
            RoteiroEstruturado com blocos narrativos
        """
        metrics = roteirista_logger.start_operation(
            operation="gerar_roteiro", ideia_id=ideia_id
        )

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
                    usuario_parts.append(
                        f"Título anterior: {estrutura_ant.get('titulo', 'N/A')}"
                    )
                    usuario_parts.append(
                        f"Duração anterior: {estrutura_ant.get('duracao_total_segundos', 'N/A')}s"
                    )
                    usuario_parts.append(
                        f"Número de blocos anteriores: {len(blocos_ant)}"
                    )
                    ultimo_bloco = blocos_ant[-1]
                    usuario_parts.append(
                        f"Último bloco anterior: {ultimo_bloco.get('conteudo', '')[:150]}..."
                    )

            if revision_source is not None and revision_feedback is not None:
                import json

                usuario_parts.append("\n=== REGENERAÇÃO VERSIONADA ===")
                usuario_parts.append(
                    f"Feedback editorial do operador:\n{revision_feedback}"
                )
                usuario_parts.append(
                    "Versão anterior a revisar (preserve os pontos que o feedback não pede para mudar):\n"
                    + json.dumps(revision_source, ensure_ascii=False)
                )

            usuario_message = "\n".join(usuario_parts)

            composed = (
                PromptBuilder(workflow=workflow, profile=profile)
                .with_niche(prompt_roteiro)
                .with_author_briefing(author_briefing)
                .with_grounding(contexto_grounding)
                .with_duration_contract(duration_contract_prompt)
                .build(task_context=usuario_message)
            )
            composed.trace["model"] = llm_gateway.model_for(LLMTaskRole.WRITING)
            composed.trace["model_gateway"] = "9router"

            resposta_llm = await self._call_llm(
                messages=[
                    {"role": "system", "content": composed.system},
                    {"role": "user", "content": composed.user},
                ],
                temperature=0.8,
                prompt_identity=composed.trace.get("identity"),
            )
            dados = validate_model_output(ScriptLLMOutput, resposta_llm)
            assert isinstance(dados, ScriptLLMOutput)

            blocos = []
            duracao_total_calculada = 0
            for bloco in dados.blocos:
                visual_queries = []
                if workflow.structured_visual_queries:
                    visual_queries = [
                        VisualQuery(
                            order=index,
                            intent=query.intent.value,
                            query=query.query,
                            narration_excerpt=query.narration_excerpt,
                            importance=query.importance.value,
                            source_note_id=query.source_note_id,
                            desired_duration_seconds=query.desired_duration_seconds,
                            notes=query.notes,
                        )
                        for index, query in enumerate(bloco.visual_queries)
                    ]
                blocos.append(
                    BlocoNarrativo(
                        tipo=bloco.tipo,
                        duracao_segundos=bloco.duracao_segundos,
                        conteudo=bloco.conteudo,
                        dicas_visual=bloco.dicas_visual,
                        dicas_audio=bloco.dicas_audio,
                        visual_queries=visual_queries,
                        purpose=bloco.purpose,
                        beats=[item.model_dump(mode="json") for item in bloco.beats],
                        claims=[item.model_dump(mode="json") for item in bloco.claims],
                        audio_intent=(
                            bloco.audio_intent.model_dump(mode="json")
                            if bloco.audio_intent is not None
                            else None
                        ),
                    )
                )
                duracao_total_calculada += bloco.duracao_segundos

            # Duração final: o que o modelo produziu de fato, respeitando só um piso
            # técnico de segurança — NUNCA um mínimo editorial artificial por perfil.
            duracao_final = max(
                dados.duracao_total_segundos,
                duracao_total_calculada,
                self._PISO_TECNICO_SEGUNDOS,
            )

            resultado = RoteiroEstruturado(
                titulo=dados.titulo[:80],
                duracao_total_segundos=duracao_final,
                blocos=blocos,
                tags=dados.tags,
                referencias=dados.referencias,
                justificativa_llm=dados.justificativa,
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
            elif (
                target_max is not None
                and duracao_final > target_max
                and not duracao_policy.allow_extended
            ):
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
                warning=warning_msg,
            )

            roteirista_logger.end_operation(
                metrics=metrics,
                success=True,
                num_blocos=len(blocos),
                duracao_total_segundos=resultado.duracao_total_segundos,
            )

            return resultado

        except Exception as e:
            roteirista_logger.end_operation(
                metrics=metrics, success=False, error=str(e)
            )
            raise

    def to_dict(self, roteiro: RoteiroEstruturado) -> dict:
        """Converte RoteiroEstruturado para dicionário (JSON)."""
        return {
            "production_script_schema_version": "2.1",
            "titulo": roteiro.titulo,
            "duracao_total_segundos": roteiro.duracao_total_segundos,
            "blocos": [
                {
                    "tipo": b.tipo,
                    "duracao_segundos": b.duracao_segundos,
                    "conteudo": b.conteudo,
                    "dicas_visual": b.dicas_visual,
                    "dicas_audio": b.dicas_audio,
                    "visual_queries": [vq.to_dict() for vq in b.visual_queries],
                    "purpose": b.purpose,
                    "beats": b.beats,
                    "claims": b.claims,
                    "audio_intent": b.audio_intent,
                    "display_title": b.display_title,
                }
                for b in roteiro.blocos
            ],
            "tags": roteiro.tags,
            "referencias": roteiro.referencias,
            "justificativa_llm": roteiro.justificativa_llm,
            "prompt_trace": roteiro.prompt_trace,
            "media_context": roteiro.media_context,
            "duration_contract": roteiro.duration_contract,
            "editorial_quality": roteiro.editorial_quality,
        }


roteirista_service = RoteiristaService()
