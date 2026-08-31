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
`media_project_id` e o filtro opcional `media_session_ids`. Esses IDs são os mesmos recebidos na
requisição e permitem ao Orchestrator executar o Visual Director sem pesquisar projetos alheios.
Roteiros antigos e fluxos sem Media Indexer continuam válidos com `media_context: null`; nenhum
payload de Semantic Timeline é copiado para o roteiro.

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

Roteiros formam histórico imutável. Edição humana de título/blocos editoriais e “regenerar com
feedback” criam uma nova `versao`, ligam `parent_roteiro_id` e preservam a versão anterior. Edição
humana não permite trocar IDs, timestamps ou provenance das `visual_queries`; aprovação só é
permitida para o draft mais recente. Roteiros históricos sem briefing ou VisualQueries continuam
válidos.

Novas gerações resolvem uma intenção de duração explícita (`explicit_target`, `profile_default`
ou `content_driven`) e podem executar como jobs duráveis por seção. Planejamento hierárquico,
retomada, routing de modelos e disciplina de evidência estão documentados em
[`docs/EDITORIAL_GENERATION_V3.md`](docs/EDITORIAL_GENERATION_V3.md).

O schema é evoluído pela revisão Alembic `0003_author_briefing`. Ela apenas acrescenta colunas
nullable/compatíveis e classifica roteiros históricos como `legacy`; não requer recriar o banco.
