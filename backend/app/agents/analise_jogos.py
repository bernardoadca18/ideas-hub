"""
Agente de Análise de Jogos - Transforma anotações de gameplay em roteiro de análise.

Workflow independente do funil padrão Trend -> Ideia -> Roteiro: a fonte é o material
fornecido diretamente pelo autor (anotações de sessões de jogo), não pesquisa/ideação
automática. Reaproveita as mesmas dataclasses de roteiro (RoteiroEstruturado,
BlocoNarrativo) para não exigir nenhuma mudança de schema de Roteiro.
"""
import time

import httpx

from app.core.config import settings
from app.core.logging import roteirista_logger
from app.core.retry import retry_llm, retry_tavily
from app.production_profiles import get_profile, GAME_ANALYSIS
from app.prompts.builder import PromptBuilder
from app.prompts.workflows import get_workflow
from app.agents.roteirista import RoteiroEstruturado, BlocoNarrativo


class AnaliseJogosService:
    """Serviço de geração de roteiros de análise de jogos a partir de anotações."""

    def __init__(self):
        self.litellm_base_url = settings.litellm_base_url
        self.litellm_api_key = settings.litellm_master_key or "dummy-key"
        self.tavily_api_key = settings.tavily_api_key
        self.llm_model = settings.llm_model

    @retry_llm()
    async def _call_llm(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 16000) -> str:
        start_time = time.time()
        tokens_used = None
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
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
                    model=self.llm_model, tokens_used=tokens_used,
                    duration=round(duration, 3), success=True,
                )
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            duration = time.time() - start_time
            roteirista_logger.log_llm_call(
                model=self.llm_model, tokens_used=tokens_used,
                duration=round(duration, 3), success=False, error=str(e),
            )
            raise

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
                        "query": query, "max_results": max_results,
                        "include_answer": True, "include_raw_content": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                parts = []
                if data.get("answer"):
                    parts.append(f"Resumo: {data['answer']}")
                for r in data.get("results", [])[:3]:
                    parts.append(f"- {r.get('title', '')}: {r.get('content', '')[:200]}")
                return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    async def gerar_roteiro_de_notas(
        self,
        titulo_provisorio: str,
        anotacoes: str,
        nome_jogo: str | None = None,
        prompt_nicho: str | None = None,
        usar_grounding: bool = False,
    ) -> RoteiroEstruturado:
        """
        Transforma anotações brutas de gameplay em um roteiro de análise estruturado.

        Args:
            titulo_provisorio: título de referência (o modelo pode propor um melhor)
            anotacoes: texto bruto das anotações do autor (pode ser longo)
            nome_jogo: nome do jogo, se não estiver claro no título
            prompt_nicho: prompt_roteiro do nicho, se este canal tiver um configurado
            usar_grounding: liga grounding factual pontual (desligado por padrão neste perfil)
        """
        profile = get_profile(GAME_ANALYSIS.id)
        workflow = get_workflow(profile.workflow_roteiro)

        contexto_grounding = ""
        if usar_grounding and nome_jogo:
            contexto_grounding = await self._search_tavily(f"{nome_jogo} data de lançamento estúdio desenvolvedor")

        usuario_parts = [f"Título provisório do vídeo: {titulo_provisorio}"]
        if nome_jogo:
            usuario_parts.append(f"Jogo analisado: {nome_jogo}")
        usuario_parts.append("\nAnotações brutas do autor (fonte primária, prioridade máxima):\n")
        usuario_parts.append(anotacoes)
        usuario_message = "\n".join(usuario_parts)

        composed = (
            PromptBuilder(workflow=workflow, profile=profile)
            .with_niche(prompt_nicho)
            .with_grounding(contexto_grounding)
            .build(task_context=usuario_message)
        )

        resposta_llm = await self._call_llm(
            messages=[
                {"role": "system", "content": composed.system},
                {"role": "user", "content": composed.user},
            ],
            temperature=0.7,
        )

        import json
        texto = resposta_llm
        if "```json" in texto:
            texto = texto.split("```json")[1].split("```")[0]
        elif "```" in texto:
            texto = texto.split("```")[1].split("```")[0]

        dados = json.loads(texto.strip())

        blocos = []
        duracao_total = 0
        for b in dados.get("blocos", []):
            duracao_bloco = b.get("duracao_segundos", 60)
            blocos.append(BlocoNarrativo(
                tipo=b.get("tipo", "desenvolvimento"),
                duracao_segundos=duracao_bloco,
                conteudo=b.get("conteudo", ""),
                dicas_visual=b.get("dicas_visual"),
                dicas_audio=b.get("dicas_audio"),
            ))
            duracao_total += duracao_bloco

        return RoteiroEstruturado(
            titulo=dados.get("titulo", titulo_provisorio)[:80],
            duracao_total_segundos=max(dados.get("duracao_total_segundos", duracao_total), duracao_total, 60),
            blocos=blocos,
            tags=dados.get("tags", []),
            referencias=dados.get("referencias"),
            justificativa_llm=dados.get("justificativa"),
            prompt_trace=composed.trace,
        )


analise_jogos_service = AnaliseJogosService()
