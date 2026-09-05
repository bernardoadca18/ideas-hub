"""
WorkflowSpec: instruções específicas de cada etapa do pipeline. Cada workflow define
o que a tarefa deve produzir e qual é o formato JSON de saída esperado. Isso é o que
muda entre "gerar ideia bruta", "refinar ideia", "gerar roteiro padrão" e "transformar
anotações de gameplay em roteiro de análise" — o resto do prompt (base, qualidade
editorial, perfil, nicho) é compartilhado.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowSpec:
    id: str
    papel_agente: str
    instrucoes: str
    formato_saida: str
    structured_visual_queries: bool = False
    prompt_version: str = "v1"
    editorial_guidance: str | None = None


IDEACAO_BRUTA = WorkflowSpec(
    id="ideacao_bruta",
    papel_agente="um gerador de ideias de vídeo, trabalhando a partir de trends/tópicos coletados",
    instrucoes="""Gere UMA ideia de vídeo original a partir do tópico/trend fornecido.

- Mantenha relevância clara com o tópico, mas explore um ângulo específico, não o óbvio.
- Varie a abordagem em relação a outras ideias que já tenham sido geradas para o mesmo
  tópico nesta rodada (tutorial, análise, opinião, curiosidade, comparação, etc.).
- O título deve ser específico o suficiente para sinalizar do que o vídeo realmente trata
  — evite títulos genéricos demais para sustentar um vídeo interessante.""",
    formato_saida="""{
  "titulo": "Título da ideia (máximo 80 caracteres)",
  "descricao": "Descrição breve do ângulo da ideia (máximo 200 caracteres)"
}""",
)

REFINAMENTO_IDEIA = WorkflowSpec(
    id="refinamento_ideia",
    papel_agente="um curador de ideias de vídeo",
    instrucoes="""Refine a ideia bruta recebida, tornando-a mais clara e atrativa sem perder a
essência original.

- Melhore título e descrição preservando o ângulo original da ideia.
- Se houver contexto de pesquisa (grounding), use-o para tornar a ideia mais específica e
  factualmente sólida — não para mudar o ângulo.
- Se houver ideias similares já existentes, avalie objetivamente se esta é uma
  continuação/duplicata ou um tema genuinamente relacionado mas distinto.""",
    formato_saida="""{
  "titulo": "Título refinado (máximo 80 caracteres)",
  "descricao_breve": "Descrição breve (máximo 200 caracteres)",
  "justificativa": "Breve explicação objetiva das mudanças feitas"
}""",
)

ROTEIRO_PADRAO = WorkflowSpec(
    id="roteiro_padrao",
    papel_agente="um roteirista profissional de vídeos faceless para YouTube",
    instrucoes="""Escreva um roteiro completo de narração para o vídeo, dividido em blocos
narrativos coerentes.

- O número e a duração dos blocos devem ser determinados pelo conteúdo real do assunto,
  não por um template fixo. Um vídeo pode ter 4 blocos ou 9 — o que o assunto sustentar
  bem.
- Cada bloco deve ter conteúdo de narração completo e específico (não um resumo do que
  seria dito), pronto para ir direto para locução.
- Adapte a estrutura ao tipo de conteúdo (lista, narrativa linear, comparação, timeline)
  em vez de forçar todo assunto no mesmo molde.
- Se esta for uma continuação (parte 2+), abra com uma recapitulação curta e natural dos
  pontos essenciais da parte anterior — sem repetir a parte anterior inteiramente.
- IMPORTANTE: A política de duração no perfil de produção indica a duração esperada.
  Respeite essa faixa: não produza um roteiro muito mais curto que o mínimo esperado
  sem justificativa clara (assunto insuficiente). Se o assunto for rico, expanda.
- Para cada bloco, produza VisualQueries estruturadas que descrevam necessidades de
  footage ao longo da narração. Elas são intenção editorial, não seleção de arquivo.
  Use narration_excerpt copiado literalmente do próprio bloco e distribua as queries
  entre abertura, desenvolvimento e fechamento. Em faceless genérico, não invente
  source_note_id, sessão ou timestamps.""",
    formato_saida="""{
  "titulo": "Título otimizado para clareza e interesse (máximo 80 caracteres)",
  "duracao_total_segundos": "IMPORTANTE: deve respeitar a política de duração do perfil ativo (ex: 600-900s para faceless)",
  "blocos": [
    {
      "tipo": "abertura | desenvolvimento | encerramento (ou outro rótulo descritivo do papel do bloco)",
      "duracao_segundos": "Cada bloco tipicamente 60-180s, ajustado ao conteúdo",
      "conteudo": "Texto de narração COMPLETO do bloco - nunca resumo ou tópicos",
      "dicas_visual": "Sugestões concretas de imagens, vídeos, gráficos ou animações",
      "dicas_audio": "Representação humana da intenção sonora",
      "purpose": "Função narrativa explícita desta seção",
      "beats": [{"purpose": "setup/evidence/contrast/implication/transition/payoff", "key_point": "Ponto novo", "evidence_refs": ["identidade da fonte"], "target_words": 90, "retention_role": "Por que o próximo beat importa"}],
      "claims": [{"summary": "Claim auditável", "evidence_tier": "official_confirmed | official_observation | reliable_secondary | leak_authenticated | inference | speculation | unverified | author_opinion", "source_identity": "fonte ou null", "confidence": 0.8}],
      "audio_intent": {"music_enabled": true, "moods": ["investigative"], "energy": 0.45, "styles": ["electronic", "documentary"], "vocals": false, "transition": "rise", "sfx_intent": []},
      "visual_queries": [
        {
          "intent": "illustration | evidence | transition | atmosphere | comparison",
          "query": "Descrição do footage necessário, sem escolher arquivo",
          "narration_excerpt": "Trecho literal da narração relacionado",
          "importance": "required | preferred | optional",
          "source_note_id": null,
          "desired_duration_seconds": 20.0,
          "notes": "Restrições editoriais opcionais"
        }
      ]
    }
  ],
  "tags": ["tag1", "tag2", "tag3"],
  "referencias": ["fonte1", "fonte2"],
  "justificativa": "Explicação objetiva das escolhas estruturais e de ritmo, incluindo por que a duração final é adequada"
}""",
    structured_visual_queries=True,
    prompt_version="roteiro_padrao_v3",
    editorial_guidance=(
        "Organize a narração pelo conteúdo real, sem template rígido. Cada seção deve "
        "avançar a tese com prosa completa, específica e oral; preserve continuidade, "
        "evite filler e use a duração como contrato sustentado por conteúdo."
    ),
)

ROTEIRO_ANALISE_JOGOS = WorkflowSpec(
    id="roteiro_analise_jogos",
    papel_agente=(
        "um roteirista/editor que transforma anotações reais de gameplay de um jogador em "
        "um roteiro de vídeo de análise coeso, preservando fielmente a voz e as opiniões do autor"
    ),
    instrucoes="""Você vai receber anotações brutas feitas pelo autor durante e após sessões de
jogo (fatos do jogo, opiniões, críticas, elogios, observações de mecânicas, problemas
encontrados, impressões pessoais — possivelmente em ordem cronológica de jogo, com
redundância e fragmentação natural de anotações feitas ao longo do tempo).

Sua tarefa:
- Identifique os temas/argumentos maiores presentes nas anotações (ex.: level design,
  combate, narrativa, progressão, exploração, IA, direção de arte, dificuldade, pacing,
  world-building — apenas os que as anotações realmente sustentam) e organize o roteiro
  em torno desses temas, conectando observações relacionadas feitas em momentos
  diferentes do jogo.
- NÃO produza uma cronologia de sessão ("fiz isso, depois aconteceu isso, depois fui
  ali"). Preserve ordem cronológica apenas onde ela for parte do argumento ou da
  experiência que o autor quer transmitir.
- Elimine redundâncias das anotações, melhore clareza e crie transições naturais entre
  temas — mas sem perder nenhuma opinião, crítica ou conclusão relevante do autor.
- Desenvolva pontos que estejam implícitos nas anotações, sem inventar experiências,
  reações ou opiniões que o autor não registrou nem deixou razoavelmente implícitas.
  Nunca escreva algo como "fiquei impressionado quando..." se as anotações não
  indicarem essa reação.
- As anotações do autor têm prioridade máxima. Fatos verificáveis sobre o jogo (se
  houver contexto de pesquisa) podem complementar, nunca substituir ou contradizer as
  anotações.
- Distinga conteúdo importante de observações redundantes ou complementares: nem todo
  volume de anotações precisa virar roteiro — remova o que não sustenta a análise, mas
  preserve tudo que for argumento relevante mesmo que fragmentado no original.
- A duração final é determinada pela profundidade do material. IMPORTANTE: uma análise
  de jogo bem feita tipicamente tem 10-60 minutos. Se as anotações forem extensas e
  detalhadas, NÃO comprima em poucos minutos — desenvolva cada tema adequadamente.
  Vídeos de análise longos (30min, 1h, 2h+) são normais e esperados quando o material
  justifica.

CONTEXTO AUDIOVISUAL (se disponível):
- Se houver contexto audiovisual, ele serve como EVIDÊNCIA de momentos do gameplay,
  com timestamps e status de alinhamento.
- Uma anotação "matched" com timestamp significa que o sistema localizou aquela
  observação no vídeo — NÃO significa que toda interpretação subjetiva da anotação
  foi "provada" pelo vídeo.
- Uma anotação "unmatched" ou "no_candidates" NÃO invalida a anotação. Significa
  apenas que o sistema não localizou visualmente aquela observação — a anotação
  continua válida como experiência pessoal do autor.
- Timestamps são evidência de QUANDO algo aconteceu, não de QUAL a opinião do autor
  sobre isso. A opinião está nas anotações.
- Use timestamps para sugerir onde determinado footage pode ser usado, mas nunca
  transforme evidência temporal em opinião pessoal.

INCERTEZA:
- Se o autor expressou incerteza nas anotações ("parece que...", "talvez...", "não
  tenho certeza se..."), PRESERVE essa incerteza no roteiro.
- Não remova linguagem de dúvida mesmo que o contexto audiovisual tenha localizado
  o momento — localização temporal NÃO é confirmação de interpretação.
- Contexto de pesquisa (grounding) pode verificar fatos, mas NÃO confirma opiniões
  pessoais ou interpretações subjetivas do autor.

HIERARQUIA DE FONTES:
1. ANOTAÇÕES DO AUTOR — autoridade máxima sobre experiência pessoal e opiniões
2. CONTEXTO AUDIOVISUAL — evidência temporal e visual, complementa mas não substitui
3. GROUNDING/PRODUÇÃO — fatos verificáveis, nunca opiniões pessoais

NUNCA:
- Transforme informação externa em experiência pessoal do autor
- Afirme como fato algo que o autor expressou como incerteza
- Substitua anotações por resumos do contexto audiovisual
- Invente reações, opiniões ou experiências não documentadas

CONSULTAS VISUAIS ESTRUTURADAS (visual_queries):
- Para cada bloco, inclua visual_queries: uma lista de consultas estruturadas que
  expressam QUE tipo de evidência visual este segmento precisa — NÃO qual arquivo ou
  clip exato usar.
- Cada visual_query DEVE incluir:
  * intent: um destes valores exatos: "illustration", "evidence", "transition",
    "atmosphere", "comparison"
  * query: descrição em linguagem natural do footage necessário (ex.: "gameplay
    mostrando o sistema de combate em ação contra um chefe")
  * narration_excerpt: trecho curto da narração ao qual esta consulta se refere
  * importance: um destes: "required", "preferred", "optional"
  * source_note_id: ID da anotação do contexto audiovisual que originou esta consulta,
    SE a consulta foi inspirada por uma anotação específica. Use o ID exatamente como
    aparece no contexto (formato UUID). NÃO invente UUIDs.
  * desired_duration_seconds: duração alvo aproximada para o footage (opcional)
  * notes: restrições adicionais ou contexto (opcional)
- NÃO inclua preferred_session_id, preferred_start_seconds ou preferred_end_seconds
  nestes campos — o backend preencherá a partir do source_note_id usando o contexto
  audiovisual confiável.
- Se o bloco não tiver necessidade visual clara, inclua uma visual_query com
  intent="illustration" e importance="optional" descrevendo o tipo genérico de footage.
- Limite: máximo 5 visual_queries por bloco. Priorize qualidade sobre quantidade.
- source_note_id é a ÚNICA forma de referenciar o contexto audiovisual. NUNCA invente
  timestamps, UUIDs de sessão ou outras referências — apenas use source_note_id que
  exista no contexto audiovisual fornecido.""",
    formato_saida="""{
  "titulo": "Título da análise (máximo 80 caracteres)",
  "duracao_total_segundos": "Duração derivada do material - vídeos de análise tipicamente 600-3600s+ (10min-1h+)",
  "blocos": [
    {
      "tipo": "rótulo descritivo do tema/seção (ex.: 'gancho', 'level_design', 'narrativa', 'veredito')",
      "duracao_segundos": "Cada bloco de tema tipicamente 120-600s dependendo da profundidade",
      "conteudo": "Texto de narração COMPLETO do bloco - desenvolva o tema em detalhe",
      "dicas_visual": "Sugestões gerais de footage de gameplay para este trecho",
      "dicas_audio": "Sugestões de música/ritmo de narração",
      "purpose": "Função narrativa explícita desta seção",
      "beats": [{"purpose": "evidence/interpretation/contrast/transition/payoff", "key_point": "Ponto novo", "evidence_refs": ["source_note_id quando aplicável"], "target_words": 90, "retention_role": "progressão"}],
      "claims": [{"summary": "Claim auditável", "evidence_tier": "gameplay_note | author_opinion | official_confirmed | official_observation | reliable_secondary | inference | speculation | unverified", "source_identity": "source_note_id/fonte ou null", "confidence": 0.8}],
      "audio_intent": {"music_enabled": true, "moods": ["analytical"], "energy": 0.4, "styles": ["documentary"], "vocals": false, "transition": null, "sfx_intent": []},
      "visual_queries": [
        {
          "intent": "illustration | evidence | transition | atmosphere | comparison",
          "query": "Descrição em linguagem natural do footage necessário",
          "narration_excerpt": "Trecho curto da narração relacionado",
          "importance": "required | preferred | optional",
          "source_note_id": "UUID da anotação de origem (do contexto audiovisual) ou null",
          "desired_duration_seconds": 15.0,
          "notes": "Restrições ou contexto adicional (opcional)"
        }
      ]
    }
  ],
  "tags": ["tag1", "tag2"],
  "referencias": ["fonte1 (se houver grounding usado)"],
  "justificativa": "Explicação objetiva de como os temas foram identificados e organizados a partir das anotações"
}""",
    structured_visual_queries=True,
    prompt_version="roteiro_analise_jogos_v2",
    editorial_guidance=(
        "Transforme as notas reais do autor em análise temática, não em diário cronológico. "
        "A autoridade é: (1) notas humanas para experiência/opinião, (2) evidência "
        "audiovisual como apoio visual/temporal, (3) grounding externo apenas para fatos. "
        "Preserve incerteza e unmatched; matched não prova interpretação. Não invente "
        "experiência, reação, UUID ou timestamp."
    ),
)

_WORKFLOWS: dict[str, WorkflowSpec] = {
    w.id: w
    for w in [IDEACAO_BRUTA, REFINAMENTO_IDEIA, ROTEIRO_PADRAO, ROTEIRO_ANALISE_JOGOS]
}


def get_workflow(workflow_id: str) -> WorkflowSpec:
    if workflow_id not in _WORKFLOWS:
        raise ValueError(f"Workflow desconhecido: {workflow_id}")
    return _WORKFLOWS[workflow_id]
