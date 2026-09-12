# Ideas Hub API Reference

Base URL: `http://localhost:8000`

## Table of Contents

- [Health Check](#health-check)
- [Nichos](#nichos)
- [Ideias](#ideias)
- [Trends](#trends)
- [Roteiros](#roteiros)
- [Fontes Trend](#fontes-trend)

---

## Health Check

### GET /health

Check if the API is running.

**Response:**
```json
{
  "status": "healthy"
}
```

---

## Nichos

Manage content niches (e.g., "technology", "gaming", "cooking").

### GET /nichos/

List all niches with optional filters.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| skip | int | No | Number of records to skip (default: 0) |
| limit | int | No | Max records to return (default: 100, max: 100) |
| ativo | bool | No | Filter by active status |

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "nome": "Tecnologia",
    "slug": "tecnologia",
    "prompt_ideacao": "Crie ideias sobre tecnologia...",
    "prompt_roteiro": "Crie roteiros técnicos...",
    "ativo": true,
    "criado_em": "2024-01-15T10:00:00Z",
    "atualizado_em": "2024-01-15T10:00:00Z"
  }
]
```

### POST /nichos/

Create a new niche.

**Request Body:**
```json
{
  "nome": "Tecnologia",
  "slug": "tecnologia",
  "prompt_ideacao": "Crie ideias sobre tecnologia para iniciantes",
  "prompt_roteiro": "Crie roteiros técnicos e educativos",
  "ativo": true
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "nome": "Tecnologia",
  "slug": "tecnologia",
  "prompt_ideacao": "Crie ideias sobre tecnologia para iniciantes",
  "prompt_roteiro": "Crie roteiros técnicos e educativos",
  "ativo": true,
  "criado_em": "2024-01-15T10:00:00Z",
  "atualizado_em": "2024-01-15T10:00:00Z"
}
```

**Errors:**
- `400 Bad Request` - Niche with slug already exists

### GET /nichos/{nicho_id}

Get a niche by ID.

**Response:** `200 OK`

### PUT /nichos/{nicho_id}

Update a niche.

**Request Body:**
```json
{
  "nome": "Tecnologia Avançada",
  "prompt_ideacao": "Crie ideias avançadas sobre tecnologia"
}
```

**Response:** `200 OK`

**Errors:**
- `404 Not Found` - Niche not found

### DELETE /nichos/{nicho_id}

Delete a niche.

**Response:** `204 No Content`

**Errors:**
- `404 Not Found` - Niche not found

---

## Ideias

Manage content ideas with AI-powered curation.

### GET /ideias/

List all ideas with optional filters.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| skip | int | No | Number of records to skip |
| limit | int | No | Max records to return |
| nicho_id | UUID | No | Filter by niche ID |
| status | str | No | Filter by status: rascunho, aprovada, rejeitada, roteirizada |
| origem | str | No | Filter by origin: manual, trend |

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "nicho_id": "uuid",
    "origem": "manual",
    "titulo": "Como usar IA para criar vídeos",
    "descricao_breve": "Tutorial prático para iniciantes",
    "author_briefing": "Quero defender uma abordagem prática, sem tratar minha opinião como fato.",
    "author_briefing_identity": "author-briefing-v1:<sha256>",
    "status": "rascunho",
    "eh_continuacao_de": null,
    "numero_parte": null,
    "fonte_trend_id": null,
    "justificativa_llm": "Ideia original sobre IA...",
    "criado_em": "2024-01-15T10:00:00Z",
    "atualizado_em": "2024-01-15T10:00:00Z"
  }
]
```

### POST /ideias/

Create a new idea processed by the Curator Agent.

The idea goes through:
1. Tavily API grounding (if configured)
2. Similarity search in the database
3. LLM refinement with niche prompt
4. Duplicate/continuation detection

**Request Body:**
```json
{
  "titulo": "Como usar IA para criar vídeos",
  "descricao": "Tutorial prático para iniciantes que querem criar conteúdo com IA",
  "author_briefing": "Contexto editorial opcional preservado exatamente como informado.",
  "nicho_id": "uuid"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "nicho_id": "uuid",
  "origem": "manual",
  "titulo": "Como usar IA para criar vídeos - Guia Completo",
  "descricao_breve": "Tutorial completo para iniciantes criarem conteúdo com inteligência artificial",
  "author_briefing": "Contexto editorial opcional preservado exatamente como informado.",
  "author_briefing_identity": "author-briefing-v1:<sha256>",
  "status": "rascunho",
  "eh_continuacao_de": null,
  "numero_parte": null,
  "fonte_trend_id": null,
  "justificativa_llm": "Ideia refinada com contexto de mercado...",
  "criado_em": "2024-01-15T10:00:00Z",
  "atualizado_em": "2024-01-15T10:00:00Z",
  "eh_duplicada": false,
  "eh_continuacao": false,
  "ideia_similar_id": null,
  "ideia_similar_titulo": null,
  "similaridade": null
}
```

**Curator Response Fields:**
- `eh_duplicada` - True if idea is a duplicate (similarity >= 0.95)
- `eh_continuacao` - True if idea is a continuation (similarity 0.85-0.94)
- `ideia_similar_id` - ID of the similar idea found
- `ideia_similar_titulo` - Title of the similar idea
- `similaridade` - Similarity score (0-1)

### GET /ideias/{ideia_id}

Get an idea by ID.

**Response:** `200 OK`

### PUT /ideias/{ideia_id}

Update an idea.

**Request Body:**
```json
{
  "titulo": "Título atualizado",
  "descricao_breve": "Descrição atualizada",
  "author_briefing": "Nova posição/contexto deliberado do autor.",
  "eh_continuacao_de": "uuid-da-ideia-anterior",
  "numero_parte": 2
}
```

**Response:** `200 OK`

### DELETE /ideias/{ideia_id}

Delete an idea.

**Response:** `204 No Content`

### PATCH /ideias/{ideia_id}/aprovar

Approve an idea for script generation.

**Response:** `200 OK`

**Errors:**
- `400 Bad Request` - Idea is not in "rascunho" status
- `404 Not Found` - Idea not found

### PATCH /ideias/{ideia_id}/rejeitar

Reject an idea.

**Response:** `200 OK`

**Errors:**
- `400 Bad Request` - Idea is not in "rascunho" status
- `404 Not Found` - Idea not found

### POST /ideias/{ideia_id}/roteiro

Generate a script from an approved idea.

The script is generated by the Screenwriter Agent with:
- Tavily API grounding (if configured)
- Narrative blocks structure
- Visual and audio tips
- If continuation (part 2+), uses previous script as context
- The current Author Briefing as editorial intent, snapshotted verbatim with a deterministic identity

**Response:** `201 Created`
```json
{
  "ideia_id": "uuid",
  "roteiro_id": "uuid",
  "versao": 1,
  "titulo": "Como usar IA para criar vídeos",
  "duracao_total_segundos": 180,
  "num_blocos": 3,
  "status": "rascunho"
}
```

**Errors:**
- `400 Bad Request` - Idea is not approved

### POST /ideias/{ideia_id}/manual-draft-improvement-runs

Persist a pasted human draft and enqueue its Editorial V3 improvement as one
transactional operation. The Idea must be approved.

**Request Body:**
```json
{
  "draft_text": "Texto humano completo, com parágrafos preservados.",
  "feedback": "Preserve especialmente a comparação central.",
  "idempotency_key": "stable-client-generated-key",
  "model_strategy": "standard"
}
```

**Response:** `202 Accepted`. Returns `draft` (the immutable `manual_create`
parent) and `run` (a normal durable generation run with
`generation_intent=revision`). Repeating the same key and payload returns the
same lineage instead of creating another draft or expensive job.

---

## Trends

Manage collected trends from various sources.

### GET /trends/

List all collected trends with optional filters.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| skip | int | No | Number of records to skip |
| limit | int | No | Max records to return |
| nicho_id | UUID | No | Filter by niche ID |
| status | str | No | Filter by status: pendente, aprovada, rejeitada |
| fonte | str | No | Filter by source: google_trends, reddit, youtube, rss |

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "nicho_id": "uuid",
    "fonte": "google_trends",
    "termo_bruto": "inteligência artificial",
    "termo_normalizado": "Inteligência Artificial",
    "volume_buscas": 50000,
    "tendencia": "em_alta",
    "status": "pendente",
    "metadados": {
      "category": "Technology"
    },
    "criado_em": "2024-01-15T10:00:00Z",
    "atualizado_em": "2024-01-15T10:00:00Z"
  }
]
```

### POST /trends/

Create a single trend manually.

**Request Body:**
```json
{
  "nicho_id": "uuid",
  "fonte": "manual",
  "termo_bruto": "machine learning",
  "status": "pendente"
}
```

**Response:** `201 Created`

### POST /trends/batch

Create multiple trends in batch.

**Request Body:**
```json
[
  {
    "nicho_id": "uuid",
    "fonte": "google_trends",
    "termo_bruto": "termo 1",
    "status": "pendente"
  },
  {
    "nicho_id": "uuid",
    "fonte": "google_trends",
    "termo_bruto": "termo 2",
    "status": "pendente"
  }
]
```

**Response:** `201 Created`

### POST /trends/coletar

Collect trends from all configured sources for a niche.

Executes parallel collection from:
- Google Trends
- Reddit (configured subreddits)
- YouTube (configured channels/categories)
- RSS (configured feeds)

**Request Body:**
```json
{
  "nicho_id": "uuid",
  "termos_adicionais": ["termo extra 1", "termo extra 2"]
}
```

**Response:** `201 Created`
```json
{
  "nicho_id": "uuid",
  "total_coletado": 45,
  "por_fonte": {
    "google_trends": 15,
    "reddit": 12,
    "youtube": 10,
    "rss": 8
  },
  "erros": null
}
```

### GET /trends/{trend_id}

Get a trend by ID.

**Response:** `200 OK`

### PUT /trends/{trend_id}

Update a trend.

**Response:** `200 OK`

### DELETE /trends/{trend_id}

Delete a trend.

**Response:** `204 No Content`

### PATCH /trends/{trend_id}/aprovar

Approve a trend for idea generation.

**Response:** `200 OK`

**Errors:**
- `404 Not Found` - Trend not found

### PATCH /trends/{trend_id}/rejeitar

Reject a trend.

**Response:** `200 OK`

### POST /trends/{trend_id}/gerar-ideias

Generate ideas from an approved trend.

Each approved trend generates N ideas (default: 3) that pass through the Curator Agent for duplicate/continuation detection.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| num_ideias | int | No | Number of ideas to generate (default from config) |

**Response:** `201 Created`
```json
{
  "trend_id": "uuid",
  "termo_trend": "inteligência artificial",
  "ideias_geradas": 3,
  "ideias": [
    {
      "id": "uuid",
      "titulo": "Ideia 1"
    },
    {
      "id": "uuid",
      "titulo": "Ideia 2"
    }
  ],
  "erros": null
}
```

**Errors:**
- `400 Bad Request` - Trend is not approved

---

## Roteiros

Manage generated scripts.

### GET /roteiros/

List all scripts with optional filters.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| skip | int | No | Number of records to skip |
| limit | int | No | Max records to return |
| ideia_id | UUID | No | Filter by idea ID |
| status | str | No | Filter by status: rascunho, aprovado, rejeitado |

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "ideia_id": "uuid",
    "versao": 1,
    "estrutura": {
      "titulo": "Como usar IA para criar vídeos",
      "duracao_total_segundos": 180,
      "blocos": [
        {
          "tipo": "introducao",
          "duracao_segundos": 20,
          "conteudo": "Apresentação do tema...",
          "dicas_visual": "Imagens de abertura",
          "dicas_audio": "Música suave"
        },
        {
          "tipo": "desenvolvimento",
          "duracao_segundos": 140,
          "conteudo": "Conteúdo principal...",
          "dicas_visual": "Demonstrações na tela",
          "dicas_audio": null
        },
        {
          "tipo": "conclusao",
          "duracao_segundos": 20,
          "conteudo": "Resumo e call-to-action...",
          "dicas_visual": "Cards finais",
          "dicas_audio": "Música de fechamento"
        }
      ],
      "tags": ["ia", "vídeos", "tutorial"],
      "referencias": ["fonte1.com"],
      "justificativa_llm": "Roteiro estruturado para..."
    },
    "status": "rascunho",
    "criado_em": "2024-01-15T10:00:00Z",
    "atualizado_em": "2024-01-15T10:00:00Z"
  }
]
```

### POST /roteiros/

Create a versioned manual draft. Version number, status and provenance are server-owned; extra legacy
fields are ignored by the input model.

**Request Body:**
```json
{
  "ideia_id": "uuid",
  "estrutura": {
    "titulo": "Título do roteiro",
    "duracao_total_segundos": 180,
    "blocos": [
      {"tipo": "corpo", "duracao_segundos": 180, "conteudo": "Texto narrativo"}
    ]
  }
}
```

**Response:** `201 Created`

### GET /roteiros/{roteiro_id}

Get a script by ID.

**Response:** `200 OK`

### GET /roteiros/ideia/{ideia_id}/latest

Get the latest script version for an idea.

**Response:** `200 OK`

**Errors:**
- `404 Not Found` - No script found for this idea

### POST /roteiros/{roteiro_id}/revisoes/editar

Create a new human-edited draft version. Title, narrative text, safe visual/audio tips, tags and
references are editable. Block order/count and existing VisualQuery provenance remain immutable.
The source version is preserved.

### POST /roteiros/{roteiro_id}/revisoes/regenerar

Regenerate from explicit operator `feedback`, creating a new linked version and preserving the
source. The current Author Briefing is snapshotted for the new generation.

`PUT /roteiros/{roteiro_id}` and `DELETE /roteiros/{roteiro_id}` return `409`: script history is
immutable and changes must create revisions.

### PATCH /roteiros/{roteiro_id}/aprovar

Approve a script for production.

The linked idea changes to "roteirizada" status.

**Response:** `200 OK`

**Errors:**
- `400 Bad Request` - Script cannot be approved

### PATCH /roteiros/{roteiro_id}/rejeitar

Reject a script.

The linked idea returns to "aprovada" status for new script generation.

**Response:** `200 OK`

---

## Fontes Trend

Manage trend source configurations for niches.

### GET /fontes-trend/

List all trend source configurations with optional filters.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| skip | int | No | Number of records to skip |
| limit | int | No | Max records to return |
| nicho_id | UUID | No | Filter by niche ID |
| tipo | str | No | Filter by type: google_trends, reddit, youtube, rss |
| ativo | bool | No | Filter by active status |

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "nicho_id": "uuid",
    "tipo": "reddit",
    "configuracao": {
      "subreddits": ["artificial", "MachineLearning"],
      "sort": "hot",
      "limit": 10
    },
    "ativo": true,
    "criado_em": "2024-01-15T10:00:00Z",
    "atualizado_em": "2024-01-15T10:00:00Z"
  }
]
```

### POST /fontes-trend/

Create a trend source configuration.

**Request Body for Reddit:**
```json
{
  "nicho_id": "uuid",
  "tipo": "reddit",
  "configuracao": {
    "subreddits": ["artificial", "MachineLearning"],
    "sort": "hot",
    "limit": 10
  },
  "ativo": true
}
```

**Request Body for YouTube:**
```json
{
  "nicho_id": "uuid",
  "tipo": "youtube",
  "configuracao": {
    "canais": ["channel_id_1", "channel_id_2"],
    "categorias": ["28"],
    "max_results": 10
  },
  "ativo": true
}
```

**Request Body for RSS:**
```json
{
  "nicho_id": "uuid",
  "tipo": "rss",
  "configuracao": {
    "feeds": [
      "https://example.com/feed.xml",
      "https://blog.example.com/rss"
    ]
  },
  "ativo": true
}
```

**Response:** `201 Created`

### GET /fontes-trend/{fonte_id}

Get a trend source configuration by ID.

**Response:** `200 OK`

### PUT /fontes-trend/{fonte_id}

Update a trend source configuration.

**Response:** `200 OK`

### DELETE /fontes-trend/{fonte_id}

Delete a trend source configuration.

**Response:** `204 No Content`

---

## Error Responses

All endpoints follow standard error response format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common Status Codes:**
- `200 OK` - Request successful
- `201 Created` - Resource created successfully
- `204 No Content` - Resource deleted successfully
- `400 Bad Request` - Invalid request or business rule violation
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error (Pydantic)
- `500 Internal Server Error` - Server error

---

## Workflow Summary

1. **Configure Niches** - Create niches with custom prompts
2. **Configure Sources** - Set up trend sources (Reddit, YouTube, RSS)
3. **Collect Trends** - POST /trends/coletar
4. **Review Trends** - Approve/reject collected trends
5. **Generate Ideas** - POST /trends/{id}/gerar-ideias
6. **Review Ideas** - Check for duplicates/continuations, approve/reject
7. **Generate Scripts** - POST /ideias/{id}/roteiro
8. **Review Scripts** - Approve for production or reject for re-generation
