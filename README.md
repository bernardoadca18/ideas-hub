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
