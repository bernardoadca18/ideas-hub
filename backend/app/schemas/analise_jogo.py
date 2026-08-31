"""Schemas para o workflow de Análise de Jogos (notas -> roteiro)."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.services.editorial_generation import DurationMode


class AnaliseJogoRequest(BaseModel):
    titulo_provisorio: str = Field(..., max_length=300)
    anotacoes: str = Field(..., min_length=20, max_length=500_000)
    nome_jogo: str | None = Field(None, max_length=200)
    nicho_id: UUID | None = None
    usar_grounding: bool = False
    author_briefing: str | None = Field(
        None,
        max_length=20_000,
        description="Contexto editorial opcional do autor; distinto das notas de gameplay",
    )
    target_duration_seconds: int | None = Field(default=None, ge=60, le=28_800)
    duration_mode: DurationMode = DurationMode.CONTENT_DRIVEN

    # Media Indexer integration (optional)
    media_project_id: UUID | None = Field(
        None, description="Media Indexer project ID for audiovisual context"
    )
    media_session_ids: list[UUID] | None = Field(
        None, description="Optional filter to specific Media Indexer sessions"
    )


class AnaliseJogoResponse(BaseModel):
    ideia_id: UUID
    roteiro_id: UUID
    versao: int
    titulo: str
    duracao_total_segundos: int
    num_blocos: int
    status: str
