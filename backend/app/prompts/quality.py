"""
Carta editorial de qualidade/retenção — compartilhada por qualquer prompt que produza
conteúdo destinado ao roteiro final (ideação, outline, roteiro, análise de jogos).

Esta é a implementação direta das seções 3, 4 e 24 do requisito do produto: qualidade
de escrita e retenção são requisito central, não um "nice to have" de um prompt
qualquer — por isso vivem em um componente único, reaproveitado, em vez de copiadas
(e inevitavelmente divergindo) em cada prompt individual.
"""


def editorial_quality_charter() -> str:
    return """Diretrizes de qualidade editorial e retenção (aplicam-se a todo o conteúdo gerado):

O objetivo não é apenas transmitir informação correta — é produzir algo genuinamente
interessante de assistir/ouvir. Cada parte do conteúdo precisa justificar sua presença:
pergunte-se "isto acrescenta informação, contexto, personalidade, tensão ou progressão
real?" — se não, corte, condense ou reescreva.

Evite ativamente:
- aberturas burocráticas como "Hoje vamos falar", "Neste vídeo veremos" ou "Desde os
  primórdios"; abra com tensão, contraste, descoberta, pergunta ou consequência real;
- repetir a mesma informação ou a mesma conclusão com palavras diferentes;
- introduções longas antes de chegar a algo interessante;
- parágrafos de preenchimento só para aumentar duração/contagem de palavras;
- excesso de contextualização antes de qualquer payoff;
- transições mecânicas e estrutura totalmente previsível de seção para seção;
- frases genéricas, conclusões óbvias e recap excessivo;
- ganchos de retenção artificiais e fórmulas repetidas (ex.: variações de "mas o que
  aconteceu depois vai te surpreender" usadas como muleta) — curiosidade deve vir do
  conteúdo em si, não de um truque de frase repetido;
- listas que são apenas uma sequência de itens desconectados, sem fio condutor;
- perda de ritmo em seções intermediárias.

Busque ativamente, quando o conteúdo permitir:
- progressão perceptível — o espectador deve sentir motivo real para continuar;
- perguntas levantadas que são respondidas depois, contraste, escalada, causa e
  consequência, pequenas variações de ritmo, callbacks a algo dito antes;
- ordenar as informações pela ordem mais interessante de se ouvir, não pela ordem em
  que foram pesquisadas/anotadas;
- desenvolver o suficiente os pontos importantes sem se alongar nos pontos simples;
- transições naturais entre seções, decorrentes do conteúdo, não fórmulas fixas;
- encerrar quando o conteúdo relevante foi desenvolvido — nunca perseguir uma contagem
  de palavras ou minutos artificialmente sem um contrato editorial explícito;
- quando houver contrato de duração, cumprir o orçamento com evidência, exemplos,
  contraexemplos, contexto, implicações e payoff — nunca com filler ou recap redundante.

Hierarquia e natureza do contexto:
- AUTHOR BRIEFING é intenção, opinião e contexto editorial deliberado do autor;
- GAMEPLAY NOTES são observações e evidências humanas autoritativas da experiência;
- MEDIA INDEXER fornece evidência audiovisual/técnica e nunca opinião editorial;
- GROUNDING EXTERNO pode sustentar fatos verificáveis, não transformar opinião em fato.
Nunca invente momentos de gameplay ou timestamps e nunca apresente uma opinião do briefing
como consenso ou fato estabelecido sem evidência factual independente.
Preserve também o grau de certeza: observação oficial não confirma automaticamente uma
mecânica; diferencie fonte oficial, fonte secundária, leak autenticado, inferência,
especulação e informação não verificada na linguagem usada pelo roteiro.

Isto não deve virar clickbait: técnicas de retenção precisam parecer parte natural do
conteúdo, nunca manipulação explícita ou óbvia ao espectador."""
