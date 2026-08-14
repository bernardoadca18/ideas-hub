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
