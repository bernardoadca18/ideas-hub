"""
Router CRUD para a entidade Ideia.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.ideia_repository import IdeiaRepository
from app.repositories.nicho_repository import NichoRepository
from app.schemas.ideia import IdeiaCreate, IdeiaUpdate, IdeiaResponse
from app.agents.curador import curador_service, IdeiaBruta
from app.services.embeddings import embedding_service


router = APIRouter(prefix="/ideias", tags=["ideias"])


def get_ideia_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> IdeiaRepository:
    return IdeiaRepository(db)


def get_nicho_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> NichoRepository:
    return NichoRepository(db)


class IdeiaBrutaInput(BaseModel):
    """Schema para entrada de ideia bruta manual."""
    titulo: str = Field(..., max_length=300, description="Título da ideia")
    descricao: str | None = Field(None, description="Descrição opcional da ideia")
    nicho_id: UUID | None = Field(None, description="ID do nicho (opcional)")


class IdeiaRefinadaResponse(IdeiaResponse):
    """Response com informações de curadoria."""
    eh_duplicada: bool = False
    eh_continuacao: bool = False
    ideia_similar_id: UUID | None = None
    ideia_similar_titulo: str | None = None
    similaridade: float | None = None


@router.get("/", response_model=list[IdeiaResponse])
async def list_ideias(
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    nicho_id: UUID | None = None,
    status: str | None = None,
    origem: str | None = None,
):
    """Lista todas as ideias com filtros opcionais."""
    return await repo.list(
        skip=skip,
        limit=limit,
        nicho_id=nicho_id,
        status=status,
        origem=origem,
    )


@router.post("/", response_model=IdeiaRefinadaResponse, status_code=201)
async def create_ideia(
    ideia_data: IdeiaBrutaInput,
    ideia_repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
    nicho_repo: Annotated[NichoRepository, Depends(get_nicho_repo)],
):
    """
    Cria uma nova ideia processada pelo Agente Curador.

    A ideia bruta passa por:
    1. Grounding via Tavily API (se configurado)
    2. Busca de similaridade no banco
    3. Refinamento via LLM com prompt do nicho (se definido)
    4. Sinalização de duplicidade/continuação

    Retorna a ideia refinada com metadados de curadoria.
    """
    # 1. Busca o nicho para obter o prompt (se nicho_id fornecido)
    prompt_nicho = None
    if ideia_data.nicho_id:
        nicho = await nicho_repo.get_by_id(ideia_data.nicho_id)
        if nicho:
            prompt_nicho = nicho.prompt_ideacao

    # 2. Gera embedding para busca de similaridade
    embedding = await embedding_service.generate_for_ideia(
        ideia_data.titulo,
        ideia_data.descricao
    )

    # 3. Busca ideias similares
    from app.core.config import settings
    similares = await ideia_repo.find_similar(
        embedding=embedding,
        threshold=settings.ideia_similarity_threshold,
        exclude_id=None,  # Nova ideia, nada a excluir
        limit=3
    )

    # Converte para formato esperado pelo curador
    ideias_similares = [
        {
            "id": str(s.id),
            "titulo": s.titulo,
            "similaridade": 1 - 0.15,  # Aproximação (distance já aplicada)
        }
        for s in similares
    ] if similares else None

    # 4. Processa via Agente Curador
    ideia_bruta = IdeiaBruta(
        titulo=ideia_data.titulo,
        descricao=ideia_data.descricao,
        nicho_id=str(ideia_data.nicho_id) if ideia_data.nicho_id else None,
        origem="manual"
    )

    ideia_refinada = await curador_service.processar(
        ideia_bruta=ideia_bruta,
        prompt_nicho=prompt_nicho,
        ideias_similares=ideias_similares,
    )

    # 5. Cria a ideia no banco com dados refinados
    # Nota: eh_continuacao_de e numero_parte são definidos manualmente pelo usuário
    # após revisão da sinalização de continuação/duplicidade
    nova_ideia_data = IdeiaCreate(
        nicho_id=ideia_data.nicho_id,
        origem="manual",
        titulo=ideia_refinada.titulo,
        descricao_breve=ideia_refinada.descricao_breve,
        status="rascunho",
        eh_continuacao_de=None,  # Definido manualmente pelo usuário
        numero_parte=None,  # Definido manualmente pelo usuário
        justificativa_llm=ideia_refinada.justificativa_llm,
    )

    ideia_criada = await ideia_repo.create(nova_ideia_data)

    # 6. Atualiza o embedding na ideia criada
    await ideia_repo.update_embedding(ideia_criada.id, embedding)

    # 7. Recarrega a ideia para garantir que todos os atributos estão disponíveis
    ideia_criada = await ideia_repo.get_by_id(ideia_criada.id)

    # 8. Prepara resposta com metadados de curadoria
    response = IdeiaRefinadaResponse(
        id=ideia_criada.id,
        nicho_id=ideia_criada.nicho_id,
        origem=ideia_criada.origem,
        titulo=ideia_criada.titulo,
        descricao_breve=ideia_criada.descricao_breve,
        status=ideia_criada.status,
        eh_continuacao_de=ideia_criada.eh_continuacao_de,
        numero_parte=ideia_criada.numero_parte,
        fonte_trend_id=ideia_criada.fonte_trend_id,
        justificativa_llm=ideia_criada.justificativa_llm,
        criado_em=ideia_criada.criado_em,
        atualizado_em=ideia_criada.atualizado_em,
        eh_duplicada=ideia_refinada.eh_duplicada,
        eh_continuacao=ideia_refinada.eh_continuacao,
        ideia_similar_id=UUID(ideia_refinada.ideia_similar_id) if ideia_refinada.ideia_similar_id else None,
        ideia_similar_titulo=ideia_refinada.ideia_similar_titulo,
        similaridade=ideia_refinada.similaridade,
    )

    return response


@router.get("/{ideia_id}", response_model=IdeiaResponse)
async def get_ideia(
    ideia_id: UUID,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """Retorna uma ideia pelo ID."""
    ideia = await repo.get_by_id(ideia_id)
    if not ideia:
        raise HTTPException(status_code=404, detail="Ideia não encontrada")
    return ideia


@router.put("/{ideia_id}", response_model=IdeiaResponse)
async def update_ideia(
    ideia_id: UUID,
    ideia_data: IdeiaUpdate,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """Atualiza uma ideia existente."""
    ideia = await repo.update(ideia_id, ideia_data)
    if not ideia:
        raise HTTPException(status_code=404, detail="Ideia não encontrada")
    return ideia


@router.delete("/{ideia_id}", status_code=204)
async def delete_ideia(
    ideia_id: UUID,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """Remove uma ideia."""
    deleted = await repo.delete(ideia_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ideia não encontrada")


@router.patch("/{ideia_id}/aprovar", response_model=IdeiaResponse)
async def aprovar_ideia(
    ideia_id: UUID,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """
    Aprova uma ideia.

    Ideias aprovadas podem ser usadas para geração de roteiros.
    """
    ideia = await repo.get_by_id(ideia_id)
    if not ideia:
        raise HTTPException(status_code=404, detail="Ideia não encontrada")

    if ideia.status != "rascunho":
        raise HTTPException(
            status_code=400,
            detail=f"Ideia não está em rascunho (status: {ideia.status})"
        )

    from app.schemas.ideia import IdeiaUpdate
    ideia_atualizada = await repo.update(ideia_id, IdeiaUpdate(status="aprovada"))
    return ideia_atualizada


@router.patch("/{ideia_id}/rejeitar", response_model=IdeiaResponse)
async def rejeitar_ideia(
    ideia_id: UUID,
    repo: Annotated[IdeiaRepository, Depends(get_ideia_repo)],
):
    """
    Rejeita uma ideia.

    Ideias rejeitadas não serão usadas para geração de roteiros.
    """
    ideia = await repo.get_by_id(ideia_id)
    if not ideia:
        raise HTTPException(status_code=404, detail="Ideia não encontrada")

    if ideia.status != "rascunho":
        raise HTTPException(
            status_code=400,
            detail=f"Ideia não está em rascunho (status: {ideia.status})"
        )

    from app.schemas.ideia import IdeiaUpdate
    ideia_atualizada = await repo.update(ideia_id, IdeiaUpdate(status="rejeitada"))
    return ideia_atualizada


class GerarRoteiroResponse(BaseModel):
    """Response da geração de roteiro."""
    ideia_id: str
    roteiro_id: str
    versao: int
    titulo: str
    duracao_total_segundos: int
    num_blocos: int
    status: str


@router.post("/{ideia_id}/roteiro", response_model=GerarRoteiroResponse, status_code=201)
async def gerar_roteiro(
    ideia_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Gera um roteiro a partir de uma ideia aprovada.

    O roteiro é gerado pelo Agente Roteirista com:
    - Grounding via Tavily API (se configurado)
    - Estrutura em blocos narrativos
    - Dicas visuais e de áudio
    - Se for continuação (parte 2+), usa roteiro anterior como contexto

    O roteiro é criado com status "rascunho" para revisão.
    """
    from app.services.roteiros.gerador_roteiro import get_roteiro_generator

    generator = get_roteiro_generator(db)

    try:
        resultado = await generator.generate_from_ideia(ideia_id=ideia_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return resultado
