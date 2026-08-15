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
            sistema_prompt = """Você é um roteirista profissional de vídeos faceless para YouTube. Sua função é criar roteiros estruturados, envolventes e com duração adequada para monetização (mínimo 10 minutos).

REGRAS OBRIGATÓRIAS DE DURAÇÃO:
- Duração total MÍNIMA: 600 segundos (10 minutos)
- Duração total ALVO: 600-720 segundos (10-12 minutos)
- Isso é CRÍTICO para monetização - respeite rigorosamente

ESTRUTURA NARRATIVA OBRIGATÓRIA:
1. GANCHO INICIAL (30-45s)
   - Promessa clara do que o espectador vai aprender/ganhar
   - Provocação ou pergunta que gere curiosidade
   - Preview dos principais pontos (em até 3 bullet points visuais)

2. INTRODUÇÃO CONTEXTUAL (60-90s)
   - Apresentação do tema com dados ou estatísticas relevantes
   - Por que isso importa AGORA (urgência/relevância)
   - O que será coberto no vídeo (roadmap)

3. DESENVOLVIMENTO PRINCIPAL (360-480s)
   - Divida em 4-6 BLOCOS DISTINCTOS, cada um focando em um aspecto específico
   - Cada bloco deve ter: explicação, exemplos práticos, dicas aplicáveis
   - Use transições claras entre blocos ("Agora que cobrimos X, vamos para Y...")
   - Inclua mini-ganchos internos para manter engajamento
   - Varie a profundidade: alguns pontos mais detalhados, outros mais práticos

4. APLICAÇÃO PRÁTICA/EXEMPLOS (60-120s)
   - Demonstre como aplicar o conhecimento em um cenário real
   - Case study ou passo-a-passo prático
   - Mostre resultados esperados ou benefícios

5. CONCLUSÃO E CALL-TO-ACTION (45-60s)
   - Recapitulação dos pontos principais (3-5 insights)
   - Pergunta para engajamento nos comentários
   - CTA para inscrição e próximo vídeo

TÉCNICAS DE ENGAGEMENT:
- Use perguntas retóricas ao longo do roteiro
- Inclua "pause aqui" para ações práticas do espectador
- Adicione elementos de surpresa ou revelação
- Mantenha linguagem conversacional e acessível
- Evite jargão excessivo - explique termos técnicos

DIRETRIZES DE CONTEÚDO:
- Cada bloco de desenvolvimento deve ter conteúdo substancial (mínimo 80 segundos)
- Evite repetições - cada ponto deve adicionar valor único
- Use dados, estatísticas ou citações para dar credibilidade
- Inclua contrapontos ou avisos quando relevante
- Termine seções com pontes para a próxima

Para continuações (parte 2+):
- Inicie com recapitulação de 30-45s da parte anterior
- Mencione pontos-chave já abordados
- Mantenha consistência de tom e terminologia

Responda APENAS no formato JSON:
{
  "titulo": "Título otimizado para SEO e CTR (máximo 80 caracteres)",
  "duracao_total_segundos": 600,
  "blocos": [
    {
      "tipo": "gancho",
      "duracao_segundos": 40,
      "conteudo": "Texto narrado completo - seja detalhado e específico",
      "dicas_visual": "Sugestões específicas de imagens, vídeos, gráficos, animações",
      "dicas_audio": "Sugestões de música, efeitos sonoros, ritmo de narração"
    }
  ],
  "tags": ["tag1", "tag2", "tag3"],
  "referencias": ["fonte1", "fonte2"],
  "justificativa": "Explicação das escolhas criativas e estrutura narrativa"
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

                # Usa duração calculada ou do JSON, garantindo mínimo de 600s
                duracao_final = max(
                    dados.get("duracao_total_segundos", duracao_total_calculada),
                    duracao_total_calculada,
                    600  # Mínimo 10 minutos para monetização
                )

                resultado = RoteiroEstruturado(
                    titulo=dados.get("titulo", ideia_titulo)[:80],
                    duracao_total_segundos=duracao_final,
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
                import traceback
                erro_detalhado = traceback.format_exc()
                print(f"Erro na geração do roteiro: {e}")
                print(f"Traceback completo:\n{erro_detalhado}")

                # Log estruturado do erro para debug
                roteirista_logger.log_llm_call(
                    model=self.llm_model,
                    tokens_used=None,
                    duration=0,
                    success=False,
                    error=f"Fallback acionado: {str(e)}"
                )

                # Fallback: cria roteiro básico de 10 minutos
                resultado = RoteiroEstruturado(
                    titulo=ideia_titulo[:80],
                    duracao_total_segundos=600,  # 10 minutos
                    blocos=[
                        BlocoNarrativo(
                            tipo="gancho",
                            duracao_segundos=40,
                            conteudo=f"Você já se perguntou como {ideia_titulo.lower()}? Neste vídeo, vou te mostrar tudo o que você precisa saber sobre isso. Vamos lá!",
                            dicas_visual="Texto animado na tela com os pontos principais",
                            dicas_audio="Música de fundo energética",
                        ),
                        BlocoNarrativo(
                            tipo="introducao",
                            duracao_segundos=90,
                            conteudo=f"Olá! Seja bem-vindo. Hoje vamos mergulhar fundo no tema: {ideia_titulo}. "
                                    f"{' ' + ideia_descricao if ideia_descricao else ''} "
                                    f"Vou cobrir todos os aspectos importantes, trazer exemplos práticos e mostrar como você pode aplicar isso. "
                                    f"Fique até o final que vou deixar uma dica especial.",
                            dicas_visual="B-roll do apresentador e gráficos de introdução",
                            dicas_audio="Música de abertura padrão",
                        ),
                        BlocoNarrativo(
                            tipo="desenvolvimento",
                            duracao_segundos=120,
                            conteudo=f"Vamos começar entendendo o contexto. {ideia_titulo} é um tema que tem ganhado cada vez mais relevância. "
                                    f"Nesta primeira parte, vou explicar os fundamentos e por que isso é importante para você. "
                                    f"Preste atenção nos detalhes que vou compartilhar.",
                            dicas_visual="Slides explicativos e animações",
                            dicas_audio="Música de fundo suave",
                        ),
                        BlocoNarrativo(
                            tipo="desenvolvimento",
                            duracao_segundos=120,
                            conteudo=f"Agora que você já entendeu o contexto, vamos para a parte prática. "
                                    f"Vou te mostrar passo a passo como isso funciona na prática e quais são os pontos que você precisa prestar atenção.",
                            dicas_visual="Demonstração prática em tela",
                            dicas_audio="SFX de transição",
                        ),
                        BlocoNarrativo(
                            tipo="desenvolvimento",
                            duracao_segundos=120,
                            conteudo=f"Continuando nossa jornada, existem alguns pontos avançados que você precisa conhecer. "
                                    f"Essas informações vão fazer diferença no seu resultado final.",
                            dicas_visual="Gráficos comparativos e diagramas",
                            dicas_audio="Música de fundo",
                        ),
                        BlocoNarrativo(
                            tipo="desenvolvimento",
                            duracao_segundos=90,
                            conteudo=f"Vou compartilhar agora alguns erros comuns que as pessoas cometem e como você pode evitá-los. "
                                    f"Essa informação é valiosa e vai te poupar muito tempo.",
                            dicas_visual="Lista visual dos erros comuns",
                            dicas_audio="SFX de alerta",
                        ),
                        BlocoNarrativo(
                            tipo="conclusao",
                            duracao_segundos=20,
                            conteudo=f"Para finalizar, vou recapitular os principais pontos que cobrimos hoje sobre {ideia_titulo}. "
                                    f"Espero que essas informações sejam úteis para você!",
                            dicas_visual="Resumo visual em bullet points",
                            dicas_audio="Música de encerramento suave",
                        ),
                    ],
                    tags=[],
                    referencias=None,
                    justificativa_llm=f"Roteiro gerado automaticamente (fallback). Erro original: {str(e)}",
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
