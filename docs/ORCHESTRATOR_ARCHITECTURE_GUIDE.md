# Orchestrator Microservice Architecture Guide

## Executive Summary

This guide provides a comprehensive blueprint for designing and implementing an orchestrator microservice that will manage the content production workflow between the existing ideas-hub service and a future production service. The orchestrator's primary responsibility is to track approved scripts (roteiros) from ideas-hub and progress them through the production pipeline.

---

## 1. Current Architecture Overview

### 1.1 Ideas-Hub Service Structure

**Technology Stack:**
- **Backend**: FastAPI (Python 3.x) with async/await patterns
- **Database**: PostgreSQL 16 with pgvector extension for embeddings
- **ORM**: SQLAlchemy 2.0 with async support
- **Frontend**: Vite + React + TypeScript
- **Containerization**: Docker Compose with three services (db, backend, frontend)

**Key Architectural Patterns:**
1. **Repository Pattern**: Data access layer abstracted through repository classes (e.g., `RoteiroRepository`, `IdeiaRepository`)
2. **Schema/Model Separation**: Pydantic schemas for API contracts, SQLAlchemy models for database representation
3. **Dependency Injection**: FastAPI's `Depends()` for session management and repository instantiation
4. **Async-first Design**: All database operations and API endpoints use async/await
5. **Configuration via Environment**: Centralized settings through `pydantic-settings`

**Service Ports:**
- Backend API: 8000
- Frontend SPA: 5173
- PostgreSQL: 5432

**Container Names:**
- Database: `ideas-hub-db`
- Backend: `ideas-hub-backend`
- Frontend: `ideas-hub-frontend`

### 1.2 Current Data Flow

```
Trend Sources → TrendColetada → Ideia → Roteiro (Script)
                  (pendente)    (rascunho)  (rascunho)
                  (aprovada)    (aprovada)  (aprovado)
                  (rejeitada)   (rejeitada) (rejeitado)
                                (em_roteiro)
                                (roteirizada)
                                (produzida)
```

### 1.3 Integration Points

**Available API Endpoints for Orchestrator:**

From `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/api/routers/roteiros.py`:
- `GET /roteiros/?status=aprovado` - Lists approved scripts ready for production
- `GET /roteiros/{id}` - Get specific script details
- `PATCH /roteiros/{id}/aprovar` - Approve a script (sets ideia status to "roteirizada")
- `PATCH /roteiros/{id}/rejeitar` - Reject a script (sets ideia status back to "aprovada")

From `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/api/routers/ideias.py`:
- `GET /ideias/?status=roteirizada` - Lists ideas with approved scripts
- `GET /ideias/?status=produzida` - Lists ideas that have completed production

---

## 2. Data Model Specifications

### 2.1 Critical Roteiro (Script) Structure

**From `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/schemas/roteiro.py` and models:**

```typescript
interface Roteiro {
  id: string;                    // UUID
  ideia_id: string;              // UUID - reference to parent idea
  versao: number;                // Version number (unique per ideia_id)
  estrutura: RoteiroEstrutura;   // JSONB - script content
  status: "rascunho" | "aprovado" | "rejeitado";
  criado_em: string;             // ISO timestamp
  atualizado_em: string;         // ISO timestamp
}

interface RoteiroEstrutura {
  titulo: string;
  duracao_total_segundos: number;
  blocos: BlocoNarrativo[];
  tags: string[];
  referencias?: string[];
  justificativa_llm?: string;
}

interface BlocoNarrativo {
  tipo: string;                  // e.g., "introducao", "desenvolvimento", "conclusao"
  duracao_segundos: number;
  conteudo: string;              // The actual script text for this block
  dicas_visual?: string;         // Visual direction hints
  dicas_audio?: string;          // Audio direction hints
}
```

**Key Constraints:**
- Unique constraint on `(ideia_id, versao)` - allows multiple script versions per idea
- Status transitions: `rascunho → aprovado | rejeitado`
- When a script is approved, the parent ideia status changes to `roteirizada`

### 2.2 Related Ideia Structure

**From `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/models/ideia.py`:**

```typescript
interface Ideia {
  id: string;
  nicho_id?: string;             // Optional reference to niche
  origem: "manual" | "trend" | "llm" | "notas_gameplay";
  titulo: string;
  descricao_breve?: string;
  status: "rascunho" | "aprovada" | "rejeitada" | "em_roteiro" | "roteirizada" | "produzida";
  eh_continuacao_de?: string;    // Self-reference for multi-part content
  numero_parte?: number;         // Part number if continuation
  fonte_trend_id?: string;       // Source trend if applicable
  justificativa_llm?: string;    // LLM justification for generated ideas
}
```

**Status Flow for Orchestrator:**
- `roteirizada` → Idea has an approved script, ready for production workflow
- `produzida` → Idea has completed production (final state)

### 2.3 Production Profiles Reference

**From `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/production_profiles.py`:**

Available profiles:
1. `faceless_pop_culture_lists` - Structured list/ranking formats
2. `faceless_informational` - Educational/technical content
3. `faceless_general` - General purpose with editorial freedom
4. `faceless_pop_culture` - Analysis, theories, retrospectives
5. `game_analysis` - Uses gameplay notes, no automatic grounding

**Profile Metadata Available:**
- Duration policies (target min/max seconds, hard minimum, guidance)
- Editorial rules
- Workflow specification (e.g., "roteiro_padrao", "roteiro_analise_jogos")
- Grounding behavior flags

---

## 3. API Contracts

### 3.1 Ideas-Hub API Client Pattern

**From `/home/bernardo/workspaces/neovids/ideas-hub/frontend/src/api/client.ts`:**

The frontend uses a typed API client class with:
- Base URL configuration via environment variable `VITE_API_URL`
- Generic `request<T>()` method with error handling
- Separate methods per entity/operation
- Query parameter building via `URLSearchParams`
- JSON serialization for request bodies

**Key Methods for Orchestrator:**
```typescript
// Get approved scripts
async getRoteiros(params?: { status?: string }): Promise<Roteiro[]>

// Get specific script
async getRoteiro(id: string): Promise<Roteiro>

// Get ideas by status
async getIdeias(params?: { status?: string; nicho_id?: string }): Promise<Ideia[]>
```

### 3.2 Backend Repository Pattern

**From `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/repositories/roteiro_repository.py`:**

```python
class RoteiroRepository:
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        ideia_id: UUID | None = None,
        status: str | None = None,
    ) -> Sequence[Roteiro]

    async def get_by_id(self, roteiro_id: UUID) -> Roteiro | None
    async def get_latest_version_by_ideia(self, ideia_id: UUID) -> Roteiro | None
```

**Filtering Pattern:**
- Uses SQLAlchemy's `select()` with `where()` clauses
- Supports multiple filters via `and_()`
- Orders by `criado_em.desc()` by default
- Pagination via `offset()` and `limit()`

---

## 4. Workflow State Machine Design Considerations

### 4.1 Current Ideas-Hub State Machine

**Ideia Status Transitions:**
```
rascunho → aprovada → em_roteiro → roteirizada → produzida
    ↓          ↓           ↓
rejeitada  rejeitada   (rejeitado returns to aprovada)
```

**Roteiro Status Transitions:**
```
rascunho → aprovado
    ↓
rejeitado
```

### 4.2 Orchestrator Workflow States (Design Recommendation)

The orchestrator should introduce intermediate production states between `roteirizada` and `produzida`. Recommended state machine:

```
roteirizada (Ideia status in ideas-hub)
     ↓
agendada_producao (Orchestrator tracks this)
     ↓
em_producao (Sent to production service)
     ↓
producao_concluida (Received from production service)
     ↓
produzida (Synced back to ideas-hub)
```

**State Management Options:**

**Option A: Orchestrator Owns Workflow State**
- Orchestrator maintains its own `WorkflowExecucao` table
- Stores `ideia_id` and `roteiro_id` as references
- Tracks production-specific metadata (assets, render progress, etc.)
- Pro: Complete autonomy, can evolve independently
- Con: Requires sync mechanisms with ideas-hub

**Option B: Extended Status in Ideas-Hub**
- Add new statuses to ideas-hub's Ideia enum
- Orchestrator calls PATCH endpoints to update status
- Pro: Single source of truth
- Con: Tight coupling, requires ideas-hub changes for production-specific states

**Option C: Hybrid Approach (Recommended)**
- Orchestrator maintains its own workflow state
- Ideas-hub Ideia status remains `roteirizada` until production fully complete
- On production completion, orchestrator updates ideas-hub to `produzida`
- Pro: Loose coupling, clear boundaries, can track production-specific metadata

### 4.3 Workflow State Data Model (Proposed)

```typescript
interface WorkflowExecucao {
  id: string;
  ideia_id: string;              // Reference to ideas-hub
  roteiro_id: string;            // Reference to ideas-hub
  status: "agendada" | "em_producao" | "concluida" | "erro";
  perfil_producao: string;       // From ideas-hub's production profiles
  prioridade: number;            // Queue priority
  agendado_em: string;
  inicio_producao_em?: string;
  conclusao_em?: string;
  erro_mensagem?: string;
  tentativas: number;
  max_tentativas: number;
  metadados?: {                  // Production-specific data
    assets_gerados?: string[];
    video_url?: string;
    duracao_final_segundos?: number;
  };
}
```

---

## 5. Integration Architecture Patterns

### 5.1 Service Communication Patterns

**Option A: Synchronous REST API Calls**
- Orchestrator calls ideas-hub `/roteiros/?status=aprovado` to fetch queue
- Orchestrator calls ideas-hub `/ideias/{id}` to update status
- Simple, direct, easy to debug
- Con: Coupled to ideas-hub availability, no retry/recovery built-in

**Option B: Shared Database (Anti-pattern for microservices)**
- Direct database access across services
- Pro: Simple queries
- Con: Tight coupling, violates microservice autonomy, schema changes break multiple services

**Option C: Message Queue (Recommended for production)**
- Ideas-hub publishes `RoteiroAprovado` events to queue
- Orchestrator consumes events and creates workflow entries
- Production service consumes work items from orchestrator
- Pro: Decoupled, reliable, supports retry/recovery, async processing
- Con: Infrastructure complexity (RabbitMQ, Redis, or Kafka)

**Option D: Event Sourcing + REST Fallback**
- Orchestrator polls ideas-hub for approved scripts (REST)
- Orchestrator publishes production events to queue
- Pro: Simple initial implementation, can evolve to event-driven
- Con: Polling overhead, eventual consistency

**Recommendation**: Start with Option D (polling + event publishing), evolve to Option C when scale demands.

### 5.2 Data Synchronization Strategy

**Reference Data (Read-only from ideas-hub):**
- Roteiro details (via GET `/roteiros/{id}`)
- Ideia metadata (via GET `/ideias/{id}`)
- Production profile configurations (could be duplicated in orchestrator for autonomy)

**State Updates (Write to ideas-hub):**
- Update Ideia status to `produzida` via PATCH `/ideias/{id}` endpoint
- Or: Orchestrator never writes to ideas-hub, just tracks its own state

**Recommendation**: Orchestrator should cache necessary roteiro data to avoid frequent API calls. Use webhooks or polling to detect new approved scripts.

---

## 6. Technical Constraints and Patterns to Follow

### 6.1 Must Follow Patterns

**Backend Structure (from ideas-hub):**
```
backend/
├── app/
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── repositories/     # Data access layer
│   ├── services/         # Business logic
│   ├── api/
│   │   └── routers/      # FastAPI route handlers
│   └── core/
│       ├── config.py     # Settings via pydantic-settings
│       ├── database.py   # Async session management
│       └── logging.py    # Structured logging
├── alembic/              # Database migrations
└── tests/                # pytest with async support
```

**Configuration Pattern:**
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    database_url: str
    api_port: int
    cors_origins: str
    ideas_hub_api_url: str  # For calling ideas-hub
```

**Repository Pattern:**
```python
class WorkflowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, workflow_data: WorkflowCreate) -> WorkflowExecucao:
        # Implementation
    
    async def get_by_ideia_id(self, ideia_id: UUID) -> WorkflowExecucao | None:
        # Implementation
```

**Dependency Injection:**
```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

def get_workflow_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> WorkflowRepository:
    return WorkflowRepository(db)
```

### 6.2 Docker Compose Structure

**Pattern from `/home/bernardo/workspaces/neovids/ideas-hub/docker-compose.yml`:**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    container_name: orchestrator-db
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
    ports:
      - "5433:5432"  # Different port to avoid conflict
    volumes:
      - orchestrator-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    container_name: orchestrator-backend
    env_file: .env
    ports:
      - "${API_PORT:-8001}:8000"  # Different port
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build: ./frontend
    container_name: orchestrator-frontend
    env_file: .env
    ports:
      - "5174:5173"  # Different port
    depends_on:
      - backend

volumes:
  orchestrator-db-data:
    name: orchestrator-db-data
```

### 6.3 Frontend Patterns

**From `/home/bernardo/workspaces/neovids/ideas-hub/frontend/src/pages/Roteiros.tsx`:**

- React functional components with hooks
- `useState` for local state management
- `useEffect` for data loading
- Async/await for API calls
- Error handling with try/catch
- Status filtering via dropdown
- Modal pattern for detail views
- Card-based list display with action buttons

**API Client Pattern:**
- Centralized typed client class
- Environment-based API URL configuration
- Generic request method with error handling
- Entity-specific methods

---

## 7. Open Questions for Architect to Resolve

### 7.1 Critical Design Decisions

1. **Database Architecture**
   - Should orchestrator maintain its own database with workflow state?
   - Should it cache roteiro/ideia data locally or always fetch from ideas-hub?
   - How to handle schema evolution across services?

2. **Communication Protocol**
   - REST polling vs message queue for fetching approved scripts?
   - Should orchestrator publish events when workflow state changes?
   - How to handle ideas-hub downtime during production scheduling?

3. **Frontend Integration**
   - Standalone orchestrator UI or embedded component in ideas-hub?
   - Shared component library between services?
   - Authentication/authorization strategy (if needed)?

4. **Production Service Handoff**
   - What data format does production service expect?
   - How to queue work items for production service?
   - How to receive completion/error notifications?

5. **Workflow Recovery**
   - How to handle failed production jobs?
   - Retry strategy and maximum attempts?
   - Manual intervention interface?

6. **State Consistency**
   - What happens if ideas-hub updates a roteiro after it's in production?
   - Version control for scripts in production queue?
   - How to handle roteiro deletion while in production workflow?

### 7.2 Implementation Questions

1. **Timing and Priority**
   - Should orchestrator support scheduled production (future dates)?
   - Priority queue for urgent vs regular scripts?
   - Batch processing vs individual script processing?

2. **Production Profiles Integration**
   - Should orchestrator understand production profiles?
   - How to route scripts to appropriate production pipeline based on profile?
   - Profile-specific workflow variations?

3. **Monitoring and Observability**
   - Logging standards and centralized logging?
   - Metrics collection (production time, queue depth, error rates)?
   - Health check endpoints beyond `/health`?

4. **Testing Strategy**
   - How to test integration with ideas-hub?
   - Mock ideas-hub API for orchestrator tests?
   - End-to-end workflow testing approach?

---

## 8. Recommended Implementation Sequence

### Phase 1: Minimal Viable Orchestrator
1. Set up orchestrator backend with FastAPI + PostgreSQL
2. Implement REST client to fetch approved roteiros from ideas-hub
3. Create basic `WorkflowExecucao` model and repository
4. Build simple queue endpoint to accept roteiro IDs for production
5. Create frontend page to display approved scripts and queue them

### Phase 2: Production Service Integration
1. Define API contract with production service
2. Implement work item publishing mechanism
3. Add status update endpoints for production service callbacks
4. Implement error handling and retry logic

### Phase 3: Advanced Features
1. Add message queue (RabbitMQ/Redis) for reliability
2. Implement scheduled production
3. Add priority queuing
4. Build monitoring dashboard
5. Implement workflow recovery mechanisms

---

## 9. API Endpoints to Implement in Orchestrator

### 9.1 Core Endpoints

**Workflow Management:**
```
GET    /workflow/queue              # List scripts in production queue
POST   /workflow/queue              # Add script to queue (from ideas-hub)
GET    /workflow/{id}               # Get workflow execution details
PATCH  /workflow/{id}/cancel        # Cancel queued/running workflow
PATCH  /workflow/{id}/retry         # Retry failed workflow
```

**Production Service Callbacks:**
```
PATCH  /workflow/{id}/start         # Production service marks as started
PATCH  /workflow/{id}/complete      # Production service marks as completed
PATCH  /workflow/{id}/error         # Production service reports error
```

**Dashboard/Status:**
```
GET    /dashboard/stats             # Queue stats, recent activity
GET    /dashboard/recent            # Recent workflow executions
```

### 9.2 Ideas-Hub Integration Client

```python
# backend/app/clients/ideas_hub_client.py
class IdeasHubClient:
    async def get_approved_roteiros(self) -> list[RoteiroResponse]:
        # GET /roteiros/?status=aprovado
    
    async def get_roteiro(self, roteiro_id: UUID) -> RoteiroResponse:
        # GET /roteiros/{id}
    
    async def get_ideia(self, ideia_id: UUID) -> IdeiaResponse:
        # GET /ideias/{id}
    
    async def mark_ideia_produzida(self, ideia_id: UUID) -> IdeiaResponse:
        # PATCH /ideias/{id} with status=produzida
```

---

## 10. Database Schema Proposal

### 10.1 Core Tables

```sql
-- Workflow execution tracking
CREATE TABLE workflow_execucoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ideia_id UUID NOT NULL,
    roteiro_id UUID NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'agendada',
    perfil_producao VARCHAR(50) NOT NULL,
    prioridade INTEGER DEFAULT 5,
    agendado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    inicio_producao_em TIMESTAMP,
    conclusao_em TIMESTAMP,
    erro_mensagem TEXT,
    tentativas INTEGER DEFAULT 0,
    max_tentativas INTEGER DEFAULT 3,
    metadados JSONB,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_workflow_status ON workflow_execucoes(status);
CREATE INDEX idx_workflow_ideia_id ON workflow_execucoes(ideia_id);
CREATE INDEX idx_workflow_roteiro_id ON workflow_execucoes(roteiro_id);
CREATE INDEX idx_workflow_prioridade ON workflow_execucoes(prioridade, agendado_em);

-- Constraints
ALTER TABLE workflow_execucoes
ADD CONSTRAINT chk_workflow_status 
CHECK (status IN ('agendada', 'em_producao', 'concluida', 'erro', 'cancelada'));
```

### 10.2 Optional: Cached Reference Data

```sql
-- Optional: Cache roteiro data to reduce API calls
CREATE TABLE roteiro_cache (
    id UUID PRIMARY KEY,  -- Same as ideas-hub roteiro.id
    ideia_id UUID NOT NULL,
    versao INTEGER NOT NULL,
    estrutura JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    cached_em TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_em TIMESTAMP  -- Optional TTL
);

CREATE INDEX idx_roteiro_cache_status ON roteiro_cache(status);
```

---

## 11. Environment Variables Template

```bash
# .env.example for orchestrator

# Database
POSTGRES_USER=orchestrator
POSTGRES_PASSWORD=orchestrator_secret
POSTGRES_DB=orchestrator_db
DATABASE_URL=postgresql+asyncpg://orchestrator:orchestrator_secret@localhost:5433/orchestrator_db

# API
API_PORT=8001
CORS_ORIGINS=http://localhost:5174,http://localhost:5173

# Ideas-Hub Integration
IDEAS_HUB_API_URL=http://ideas-hub-backend:8000
IDEAS_HUB_API_TIMEOUT=30

# Production Service (Future)
PRODUCTION_SERVICE_URL=http://production-service:8002
PRODUCTION_SERVICE_TIMEOUT=300

# Workflow Configuration
WORKFLOW_MAX_RETRIES=3
WORKFLOW_RETRY_DELAY_SECONDS=60
WORKFLOW_POLL_INTERVAL_SECONDS=30

# Logging
LOG_LEVEL=INFO
```

---

## 12. Key Architectural Principles

1. **Loose Coupling**: Orchestrator should not break if ideas-hub is temporarily unavailable
2. **Eventual Consistency**: Accept that data may be slightly stale between services
3. **Fail-Safe Defaults**: Graceful degradation when dependencies are down
4. **Observability First**: Log all state transitions and external calls
5. **Idempotency**: Workflow operations should be idempotent for retry safety
6. **Separation of Concerns**: Orchestrator manages workflow, not content generation
7. **Async-First**: All I/O operations should be asynchronous

---

## Critical Files for Implementation

Based on this exploration, the following files from ideas-hub are most critical for implementing the orchestrator:

- `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/api/routers/roteiros.py` - API endpoints for fetching approved scripts
- `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/schemas/roteiro.py` - Pydantic schemas defining script structure
- `/home/bernardo/workspaces/neovids/ideas-hub/frontend/src/api/client.ts` - TypeScript API client pattern to replicate
- `/home/bernardo/workspaces/neovids/ideas-hub/backend/app/repositories/roteiro_repository.py` - Repository pattern implementation to follow
- `/home/bernardo/workspaces/neovids/ideas-hub/docker-compose.yml` - Container orchestration configuration pattern
