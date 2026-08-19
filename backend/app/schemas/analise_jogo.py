"""Schemas para o workflow de Análise de Jogos (notas -> roteiro)."""
from uuid import UUID

from pydantic import BaseModel, Field


class AnaliseJogoRequest(BaseModel):
    titulo_provisorio: str = Field(..., max_length=300)
    anotacoes: str = Field(..., min_length=20)
    nome_jogo: str | None = Field(None, max_length=200)
    nicho_id: UUID | None = None
    usar_grounding: bool = False

    # Media Indexer integration (optional)
    media_project_id: UUID | None = Field(
        None,
        description="Media Indexer project ID for audiovisual context"
    )
    media_session_ids: list[UUID] | None = Field(
        None,
        description="Optional filter to specific Media Indexer sessions"
    )


class AnaliseJogoResponse(BaseModel):
    ideia_id: UUID
    roteiro_id: UUID
    versao: int
    titulo: str
    duracao_total_segundos: int
    num_blocos: int
    status: str
