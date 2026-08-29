"""
Router CRUD para a entidade Ideia.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.curador import IdeiaBruta, curador_service
from app.core.database import get_db
from app.repositories.ideia_repository import IdeiaRepository
from app.repositories.nicho_repository import NichoRepository
from app.schemas.ideia import IdeiaCreate, IdeiaResponse, IdeiaUpdate
from app.schemas.llm_outputs import LLMOutputError
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
    author_briefing: str | None = Field(
        None,
        description="Contexto editorial opcional fornecido pelo autor; não é refinado pelo Curador",
    )
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
    perfil_id = None
    if ideia_data.nicho_id:
        nicho = await nicho_repo.get_by_id(ideia_data.nicho_id)
        if nicho:
            prompt_nicho = nicho.prompt_ideacao
            perfil_id = nicho.perfil_producao

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
            "id": str(match.idea.id),
            "titulo": match.idea.titulo,
            "similaridade": match.similarity,
        }
        for match in similares
    ] if similares else None

    # 4. Processa via Agente Curador
    ideia_bruta = IdeiaBruta(
        titulo=ideia_data.titulo,
        descricao=ideia_data.descricao,
        nicho_id=str(ideia_data.nicho_id) if ideia_data.nicho_id else None,
        origem="manual"
    )

    try:
        ideia_refinada = await curador_service.processar(
            ideia_bruta=ideia_bruta,
            prompt_nicho=prompt_nicho,
            ideias_similares=ideias_similares,
            perfil_id=perfil_id,
        )
    except LLMOutputError as exc:
        raise HTTPException(
            status_code=502,
            detail={"category": exc.category, "message": exc.public_message},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "category": "provider_failure",
                "message": "O serviço de curadoria está temporariamente indisponível.",
            },
        ) from exc

    # 5. Cria a ideia no banco com dados refinados
    # Nota: eh_continuacao_de e numero_parte são definidos manualmente pelo usuário
    # após revisão da sinalização de continuação/duplicidade
    nova_ideia_data = IdeiaCreate(
        nicho_id=ideia_data.nicho_id,
        origem="manual",
        titulo=ideia_refinada.titulo,
        descricao_breve=ideia_refinada.descricao_breve,
        author_briefing=ideia_data.author_briefing,
        status="rascunho",
        eh_continuacao_de=None,  # Definido manualmente pelo usuário
        numero_parte=None,  # Definido manualmente pelo usuário
        justificativa_llm=ideia_refinada.justificativa_llm,
    )

    ideia_criada = await ideia_repo.create(nova_ideia_data)

    # 6. Atualiza o embedding na ideia criada
    await ideia_repo.update_embedding(ideia_criada.id, embedding)

    # 7. Recarrega a ideia para garantir que todos os atributos estão disponíveis
    ideia_recarregada = await ideia_repo.get_by_id(ideia_criada.id)
    assert ideia_recarregada is not None

    # 8. Prepara resposta com metadados de curadoria
    response = IdeiaRefinadaResponse(
        id=ideia_recarregada.id,
        nicho_id=ideia_recarregada.nicho_id,
        origem=ideia_recarregada.origem,
        titulo=ideia_recarregada.titulo,
        descricao_breve=ideia_recarregada.descricao_breve,
        author_briefing=ideia_recarregada.author_briefing,
        author_briefing_identity=ideia_recarregada.author_briefing_identity,
        perfil_producao=ideia_recarregada.perfil_producao,
        status=ideia_recarregada.status,
        eh_continuacao_de=ideia_recarregada.eh_continuacao_de,
        numero_parte=ideia_recarregada.numero_parte,
        fonte_trend_id=ideia_recarregada.fonte_trend_id,
        justificativa_llm=ideia_recarregada.justificativa_llm,
        criado_em=ideia_recarregada.criado_em,
        atualizado_em=ideia_recarregada.atualizado_em,
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        from app.services.roteiros.gerador_roteiro import ScriptGenerationError

        if isinstance(exc, ScriptGenerationError):
            raise HTTPException(
                status_code=502,
                detail={"category": exc.category, "message": exc.public_message},
            ) from exc
        raise

    return resultado
