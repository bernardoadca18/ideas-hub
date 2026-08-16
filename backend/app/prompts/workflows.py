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
  sem justificativa clara (assunto insuficiente). Se o assunto for rico, expanda.""",
    formato_saida="""{
  "titulo": "Título otimizado para clareza e interesse (máximo 80 caracteres)",
  "duracao_total_segundos": "IMPORTANTE: deve respeitar a política de duração do perfil ativo (ex: 600-900s para faceless)",
  "blocos": [
    {
      "tipo": "abertura | desenvolvimento | encerramento (ou outro rótulo descritivo do papel do bloco)",
      "duracao_segundos": "Cada bloco tipicamente 60-180s, ajustado ao conteúdo",
      "conteudo": "Texto de narração COMPLETO do bloco - nunca resumo ou tópicos",
      "dicas_visual": "Sugestões concretas de imagens, vídeos, gráficos ou animações",
      "dicas_audio": "Sugestões de música, efeitos sonoros ou ritmo de narração"
    }
  ],
  "tags": ["tag1", "tag2", "tag3"],
  "referencias": ["fonte1", "fonte2"],
  "justificativa": "Explicação objetiva das escolhas estruturais e de ritmo, incluindo por que a duração final é adequada"
}""",
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
  justifica.""",
    formato_saida="""{
  "titulo": "Título da análise (máximo 80 caracteres)",
  "duracao_total_segundos": "Duração derivada do material - vídeos de análise tipicamente 600-3600s+ (10min-1h+)",
  "blocos": [
    {
      "tipo": "rótulo descritivo do tema/seção (ex.: 'gancho', 'level_design', 'narrativa', 'veredito')",
      "duracao_segundos": "Cada bloco de tema tipicamente 120-600s dependendo da profundidade",
      "conteudo": "Texto de narração COMPLETO do bloco - desenvolva o tema em detalhe",
      "dicas_visual": "Sugestões de que footage de gameplay gravado usar neste trecho",
      "dicas_audio": "Sugestões de música/ritmo de narração"
    }
  ],
  "tags": ["tag1", "tag2"],
  "referencias": ["fonte1 (se houver grounding usado)"],
  "justificativa": "Explicação objetiva de como os temas foram identificados e organizados a partir das anotações"
}""",
)

_WORKFLOWS: dict[str, WorkflowSpec] = {
    w.id: w for w in [IDEACAO_BRUTA, REFINAMENTO_IDEIA, ROTEIRO_PADRAO, ROTEIRO_ANALISE_JOGOS]
}


def get_workflow(workflow_id: str) -> WorkflowSpec:
    if workflow_id not in _WORKFLOWS:
        raise ValueError(f"Workflow desconhecido: {workflow_id}")
    return _WORKFLOWS[workflow_id]
