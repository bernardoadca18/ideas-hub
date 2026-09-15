# ideas-hub

Microsserviço responsável por ideias, nichos, trends e geração de roteiros
estruturados. Autocontido: banco próprio (Postgres + pgvector), API própria
(FastAPI), frontend próprio (Vite + React + TS).

## Subir o ambiente

```bash
cp .env.example .env   # ajustar chaves e senha
docker compose up --build
```

- API: http://localhost:8000
- Frontend: http://localhost:5173
- Banco: localhost:5432

## Proveniência de mídia no Production Script

No workflow `game_analysis`, o `Roteiro.estrutura` preserva um `media_context` compacto com
`media_project_id` e uma lista opcional de `media_session_ids`. Lista ausente, nula ou vazia
significa pesquisar o projeto inteiro; quando presentes, os IDs de sessão devem ser únicos. Esses
IDs permitem ao Orchestrator executar o Visual Director sem pesquisar projetos alheios. Roteiros antigos continuam
legíveis com `media_context: null`; a exigência na entrada de produção é declarada pelo
`ProductionProfile`. O binding valida UUIDs, normaliza lista vazia e rejeita duplicatas localmente,
mas não faz lookup
síncrono no Media Indexer: indisponibilidade temporária do serviço de mídia não pode impedir edição
editorial. A consistência project/session continua validada pelo Visual Director antes da seleção.

`POST /roteiros/{id}/revisoes/vincular-midia` cria uma revisão imutável `media_binding` derivada do
ID explicitamente escolhido, preservando narração, VisualQueries e metadata editorial. O filho
herda `aprovado` somente quando o pai escolhido já estava aprovado; mudanças editoriais reais
continuam nascendo como `rascunho`. Binding idêntico é rejeitado como no-op.
`GET /roteiros/{id}/production-readiness` compõe aprovação editorial, Visual Readiness
e a policy profile-aware de MediaScope; o Orchestrator consome esse contrato antes de criar o
workflow ou enfileirar TTS.

## Author Briefing e revisões editoriais

`author_briefing` é o contexto editorial opcional escrito deliberadamente pelo autor. Ele é
independente de `descricao_breve`: a descrição resume a ideia e pode ser refinada pelo Curador; o
briefing preserva exatamente o texto informado e nunca é reescrito pelo LLM. O roteirista recebe a
hierarquia explícita de contexto: Author Briefing é intenção/opinião, gameplay notes são evidência
humana, Media Indexer é evidência audiovisual/técnica e grounding externo é informação factual.
Uma opinião no briefing não se torna fato objetivo.

Cada roteiro salva `author_briefing_snapshot` e `author_briefing_identity`. A identidade usa o
contrato versionado `author-briefing-v1`: Unicode NFC e finais de linha CRLF/CR são canônicos para
LF; nenhum outro whitespace é removido. `None` é distinto de texto vazio. Assim, o conteúdo salvo
continua verbatim, enquanto a identidade permite detectar se o briefing atual mudou depois da
geração.

Roteiros formam histórico imutável. **HUMAN APPROVAL IS SOVEREIGN. HISTORICAL REVISIONS REMAIN
USABLE. LATEST REVISION IS A DEFAULT, NOT AN AUTHORITY.** O operador pode aprovar e escolher uma
revisão histórica por seu ID exato; isso não altera nem remove revisões posteriores. Edição humana de título/blocos editoriais e “regenerar com
feedback” criam uma nova `versao`, ligam `parent_roteiro_id` e preservam a versão anterior. Blocos
cujo texto e duração não mudaram podem preservar seus requisitos visuais; blocos alterados perdem
os spans antigos e ficam explicitamente pendentes de enrichment visual. **MEDIA BINDING IS
OPERATIONAL CONFIGURATION** e workflows de produção devem fixar o ID de uma revisão imutável
exata. Roteiros históricos sem briefing ou VisualQueries continuam válidos.

## Contrato visual de produção faceless

O host segmenta deterministicamente cada seção concluída em **Visual Beats** contíguos, sem gaps
ou overlaps, com densidade definida pelo `ProductionProfile` (30 s por beat por padrão). Esse
conceito não é um shot: ele representa uma unidade editorial de coverage. Chamadas LLM bounded
em lotes de até cinco beats descrevem somente o que procurar (`query`, `intent`, `importance`,
`notes` e `source_note_id` confiável). O host materializa cada **VisualQuery** com o texto literal
completo e os offsets do beat. O Orchestrator converte esses spans textuais em tempo físico no
NarrationAlignment, o Visual Director escolhe uma fonte, e a ProductionTimeline produz os
placements concretos.

`GET /roteiros/{id}/visual-readiness` é a autoridade canônica para aptidão à produção visual. Ele
verifica coverage textual integral, ordem, identidade, semântica e provenance. `status=aprovado`
continua sendo aprovação editorial e não substitui essa readiness. Roteiros históricos sem queries
seguem legíveis e versionáveis; `/preparar-producao` cria uma revisão imutável
`visual_enrichment`, preservando a identidade do conteúdo falável. A produção final é bloqueada
antes do TTS quando a revisão aprovada não está visualmente pronta.

Novas gerações resolvem uma intenção de duração explícita (`explicit_target`, `profile_default`
ou `content_driven`) e podem executar como jobs duráveis por seção. Planejamento hierárquico,
retomada, routing de modelos e disciplina de evidência estão documentados em
[`docs/EDITORIAL_GENERATION_V3.md`](docs/EDITORIAL_GENERATION_V3.md).

O schema é evoluído pela revisão Alembic `0003_author_briefing`. Ela apenas acrescenta colunas
nullable/compatíveis e classifica roteiros históricos como `legacy`; não requer recriar o banco.
