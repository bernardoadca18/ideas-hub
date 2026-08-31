"""
Agente de Análise de Jogos - Transforma anotações de gameplay em roteiro de análise.

Workflow independente do funil padrão Trend -> Ideia -> Roteiro: a fonte é o material
fornecido diretamente pelo autor (anotações de sessões de jogo), não pesquisa/ideação
automática. Reaproveita as mesmas dataclasses de roteiro (RoteiroEstruturado,
BlocoNarrativo) para não exigir nenhuma mudança de schema de Roteiro.
"""

import json
from uuid import UUID

import httpx

from app.agents.roteirista import BlocoNarrativo, RoteiroEstruturado
from app.core.config import settings
from app.core.logging import roteirista_logger
from app.core.retry import retry_tavily
from app.production_profiles import GAME_ANALYSIS, get_profile
from app.prompts.builder import PromptBuilder
from app.prompts.workflows import get_workflow
from app.schemas.llm_outputs import ScriptLLMOutput, validate_model_output
from app.schemas.media_indexer import GameAnalysisMediaContext
from app.schemas.visual_query import VisualQuery
from app.services.llm_gateway import LLMTaskRole, llm_gateway
from app.services.media_context_provider import MediaContextProvider
from app.services.media_indexer_context_provider import MediaIndexerContextProvider


def format_media_context_for_prompt(media_context: GameAnalysisMediaContext) -> str:
    """Format media context into a compact text suitable for the LLM prompt.

    This function transforms the structured media context into a human-readable
    format that the LLM can use as supplementary evidence.

    Each note includes:
    - Note ID (for source_note_id reference in visual_queries)
    - The raw note content (primary value)
    - Alignment status and timestamp if matched
    - Confidence score
    """
    if not media_context.available:
        return ""

    parts = []

    for session in media_context.sessions:
        parts.append(f"Session: {session.session_label}")

        for note in session.notes:
            status = note.note.alignment_status
            # Include note ID for visual_query source_note_id reference
            # Format: "  Note {order} [id={uuid}]: [{status}] {raw}"
            note_text = f"  Note {note.note.order} [id={note.note.id}]: [{status}] {note.note.raw}"

            if note.alignment:
                start_min = int(note.alignment.start_seconds // 60)
                start_sec = int(note.alignment.start_seconds % 60)
                end_min = int(note.alignment.end_seconds // 60)
                end_sec = int(note.alignment.end_seconds % 60)
                note_text += (
                    f" @ {start_min:02d}:{start_sec:02d}-{end_min:02d}:{end_sec:02d}"
                )
                note_text += f" (confidence: {note.alignment.confidence:.2f})"

            parts.append(note_text)

        parts.append("")  # Empty line between sessions

    # Add warnings if any
    if media_context.warnings:
        parts.append("Warnings:")
        for warning in media_context.warnings:
            parts.append(f"  - {warning}")

    return "\n".join(parts)


class AnaliseJogosService:
    """Serviço de geração de roteiros de análise de jogos a partir de anotações."""

    def __init__(self, media_context_provider: MediaContextProvider | None = None):
        self.litellm_base_url = settings.litellm_base_url
        self.litellm_api_key = settings.litellm_master_key or "dummy-key"
        self.tavily_api_key = settings.tavily_api_key
        self._media_context_provider = media_context_provider

    @property
    def media_context_provider(self) -> MediaContextProvider:
        """Lazy initialization of media context provider."""
        if self._media_context_provider is None:
            # Only create real provider if Media Indexer is configured
            if settings.media_indexer_base_url:
                self._media_context_provider = MediaIndexerContextProvider()
            else:
                # Use fake provider that returns empty context
                from app.services.media_context_provider import FakeMediaContextProvider

                self._media_context_provider = FakeMediaContextProvider()
        return self._media_context_provider

    def _build_note_provenance_lookup(
        self, media_context: GameAnalysisMediaContext | None
    ) -> dict[UUID, tuple[UUID, float | None, float | None]]:
        """Build lookup from note ID to (session_id, start_seconds, end_seconds).

        This enables provenance canonicalization: given a source_note_id from the LLM,
        we can fill in the preferred_session_id and timestamps from the trusted
        GameAnalysisMediaContext.

        Returns:
            Dict mapping note_id -> (session_id, start_seconds, end_seconds)
        """
        lookup: dict[UUID, tuple[UUID, float | None, float | None]] = {}
        if not media_context or not media_context.available:
            return lookup

        for session in media_context.sessions:
            for note in session.notes:
                note_id = note.note.id
                session_id = session.session_id
                start_seconds = note.alignment.start_seconds if note.alignment else None
                end_seconds = note.alignment.end_seconds if note.alignment else None
                lookup[note_id] = (session_id, start_seconds, end_seconds)

        return lookup

    def _parse_visual_queries(
        self,
        visual_queries_data: list[dict] | None,
        note_lookup: dict[UUID, tuple[UUID, float | None, float | None]],
    ) -> list[VisualQuery]:
        """Parse visual_queries from LLM output with provenance canonicalization.

        This method:
        1. Parses the LLM-provided visual_query objects
        2. Validates source_note_id against the trusted note_lookup
        3. Fills preferred_session_id/timestamps from the lookup
        4. Returns a list of canonicalized VisualQuery objects

        The LLM provides source_note_id; the backend fills the rest.
        """
        if not visual_queries_data:
            return []

        queries = []
        for i, vq_data in enumerate(visual_queries_data[:5]):  # Max 5 per block
            source_note_id = None
            preferred_session_id = None
            preferred_start_seconds = None
            preferred_end_seconds = None

            # Validate and resolve source_note_id
            if vq_data.get("source_note_id"):
                try:
                    source_note_id = UUID(vq_data["source_note_id"])
                    if source_note_id in note_lookup:
                        session_id, start, end = note_lookup[source_note_id]
                        preferred_session_id = session_id
                        preferred_start_seconds = start
                        preferred_end_seconds = end
                    else:
                        roteirista_logger.logger.warning(
                            "visual_query_invalid_source_note",
                            extra={
                                "source_note_id": str(source_note_id),
                                "order": i,
                            },
                        )
                        # Keep source_note_id but don't fill provenance
                except (ValueError, TypeError) as e:
                    roteirista_logger.logger.warning(
                        "visual_query_invalid_uuid",
                        extra={
                            "source_note_id": vq_data.get("source_note_id"),
                            "error": str(e),
                        },
                    )

            query = VisualQuery(
                order=i,
                intent=vq_data.get("intent", "illustration"),
                query=vq_data.get("query", ""),
                narration_excerpt=vq_data.get("narration_excerpt"),
                importance=vq_data.get("importance", "preferred"),
                source_note_id=source_note_id,
                preferred_session_id=preferred_session_id,
                preferred_start_seconds=preferred_start_seconds,
                preferred_end_seconds=preferred_end_seconds,
                desired_duration_seconds=vq_data.get("desired_duration_seconds"),
                notes=vq_data.get("notes"),
            )
            queries.append(query)

        return queries

    async def _call_llm(
        self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 16000
    ) -> str:
        result = await llm_gateway.complete(
            messages=messages,
            role=LLMTaskRole.WRITING,
            temperature=temperature,
            max_tokens=max_tokens,
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
    async def _search_tavily(self, query: str, max_results: int = 5) -> str:
        if not self.tavily_api_key:
            return ""
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
                for r in data.get("results", [])[:3]:
                    parts.append(
                        f"- {r.get('title', '')}: {r.get('content', '')[:200]}"
                    )
                return "\n".join(parts) if parts else ""
        except Exception:  # noqa: BLE001 - optional external-grounding boundary
            return ""

    async def gerar_roteiro_de_notas(
        self,
        titulo_provisorio: str,
        anotacoes: str,
        nome_jogo: str | None = None,
        prompt_nicho: str | None = None,
        usar_grounding: bool = False,
        media_project_id: UUID | None = None,
        media_session_ids: list[UUID] | None = None,
        author_briefing: str | None = None,
        duration_contract_prompt: str | None = None,
        revision_source: dict | None = None,
        revision_feedback: str | None = None,
    ) -> RoteiroEstruturado:
        """
        Transforma anotações brutas de gameplay em um roteiro de análise estruturado.

        Args:
            titulo_provisorio: título de referência (o modelo pode propor um melhor)
            anotacoes: texto bruto das anotações do autor (pode ser longo)
            nome_jogo: nome do jogo, se não estiver claro no título
            prompt_nicho: prompt_roteiro do nicho, se este canal tiver um configurado
            usar_grounding: liga grounding factual pontual (desligado por padrão neste perfil)
            media_project_id: ID do projeto no Media Indexer para contexto audiovisual
            media_session_ids: filtro opcional para sessões específicas do Media Indexer
            author_briefing: intenção/opinião/contexto editorial distinto das notas
        """
        profile = get_profile(GAME_ANALYSIS.id)
        workflow = get_workflow(profile.workflow_roteiro)

        # Retrieve grounding context (optional)
        contexto_grounding = ""
        if usar_grounding and nome_jogo:
            contexto_grounding = await self._search_tavily(
                f"{nome_jogo} data de lançamento estúdio desenvolvedor"
            )

        # Retrieve media context (optional, fail-open)
        media_context = None
        media_context_text = ""
        if media_project_id:
            try:
                media_context = await self.media_context_provider.get_context(
                    media_project_id=media_project_id,
                    media_session_ids=media_session_ids,
                    max_chars=settings.game_analysis_media_context_max_chars,
                )
                media_context_text = format_media_context_for_prompt(media_context)

                roteirista_logger.logger.info(
                    "media_context_retrieved_for_game_analysis",
                    extra={
                        "project_id": str(media_project_id),
                        "available": media_context.available,
                        "total_notes": media_context.total_notes,
                        "matched_notes": media_context.matched_notes,
                        "unmatched_notes": media_context.unmatched_notes,
                        "total_chars": media_context.total_chars,
                    },
                )
            except Exception as e:  # noqa: BLE001 - optional Media Indexer boundary
                roteirista_logger.logger.warning(
                    "media_context_retrieval_failed",
                    extra={
                        "project_id": str(media_project_id),
                        "error": str(e),
                    },
                )
                # Fail-open: continue without media context

        # Build the user message with raw notes as primary source
        usuario_parts = [f"Título provisório do vídeo: {titulo_provisorio}"]
        if nome_jogo:
            usuario_parts.append(f"Jogo analisado: {nome_jogo}")
        usuario_parts.append(
            "\nAnotações brutas do autor (fonte primária, prioridade máxima):\n"
        )
        usuario_parts.append(anotacoes)
        if revision_source is not None and revision_feedback is not None:
            usuario_parts.append(
                "\nRevisão direcionada do rascunho anterior. Preserve as notas humanas, "
                "claims sustentados, IDs/timestamps e VisualQueries com provenance."
            )
            usuario_parts.append(f"Feedback determinístico:\n{revision_feedback}")
            usuario_parts.append(
                "Rascunho anterior:\n" + json.dumps(revision_source, ensure_ascii=False)
            )
        usuario_message = "\n".join(usuario_parts)

        composed = (
            PromptBuilder(workflow=workflow, profile=profile)
            .with_niche(prompt_nicho)
            .with_author_briefing(author_briefing)
            .with_media_context(media_context_text)
            .with_grounding(contexto_grounding)
            .with_duration_contract(duration_contract_prompt)
            .build(task_context=usuario_message)
        )
        composed.trace["model"] = llm_gateway.model_for(LLMTaskRole.WRITING)
        composed.trace["provider"] = "litellm_openai_compatible"

        resposta_llm = await self._call_llm(
            messages=[
                {"role": "system", "content": composed.system},
                {"role": "user", "content": composed.user},
            ],
            temperature=0.7,
        )

        dados = validate_model_output(ScriptLLMOutput, resposta_llm)
        assert isinstance(dados, ScriptLLMOutput)

        # Build provenance lookup for visual queries
        note_lookup = self._build_note_provenance_lookup(media_context)

        blocos = []
        duracao_total = 0
        for bloco in dados.blocos:
            duracao_bloco = bloco.duracao_segundos

            # Parse visual queries with provenance canonicalization
            visual_queries = self._parse_visual_queries(
                [item.model_dump(mode="json") for item in bloco.visual_queries],
                note_lookup,
            )

            blocos.append(
                BlocoNarrativo(
                    tipo=bloco.tipo,
                    duracao_segundos=duracao_bloco,
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
            duracao_total += duracao_bloco

        duracao_final = max(dados.duracao_total_segundos, duracao_total, 60)

        resultado = RoteiroEstruturado(
            titulo=dados.titulo[:80],
            duracao_total_segundos=duracao_final,
            blocos=blocos,
            tags=dados.tags,
            referencias=dados.referencias,
            justificativa_llm=dados.justificativa,
            prompt_trace=composed.trace,
            media_context=(
                {
                    "media_project_id": str(media_project_id)
                    if media_project_id
                    else None,
                    "media_session_ids": [str(item) for item in media_session_ids]
                    if media_session_ids
                    else None,
                }
                if media_project_id or media_session_ids
                else None
            ),
        )

        # Log de duração para análise de jogos (não há target fixo, mas é útil rastrear)
        roteirista_logger.log_duration_check(
            duracao_gerada=duracao_final,
            target_min=None,
            target_max=None,
            profile_id=profile.id,
            dentro_do_esperado=True,  # Sempre True pois não há target para game_analysis
            warning=f"Duração gerada: {duracao_final}s ({duracao_final // 60}min {duracao_final % 60}s) - derivada das anotações fornecidas",
        )

        return resultado


analise_jogos_service = AnaliseJogosService()
