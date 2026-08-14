"""
Repositório assíncrono para a entidade Ideia.
"""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ideia import Ideia
from app.schemas.ideia import IdeiaCreate, IdeiaUpdate


class IdeiaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, ideia_data: IdeiaCreate) -> Ideia:
        ideia = Ideia(**ideia_data.model_dump())
        self.session.add(ideia)
        await self.session.commit()
        await self.session.refresh(ideia)
        return ideia

    async def get_by_id(self, ideia_id: UUID) -> Ideia | None:
        result = await self.session.execute(
            select(Ideia).where(Ideia.id == ideia_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        nicho_id: UUID | None = None,
        status: str | None = None,
        origem: str | None = None,
    ) -> Sequence[Ideia]:
        query = select(Ideia)

        filters = []
        if nicho_id:
            filters.append(Ideia.nicho_id == nicho_id)
        if status:
            filters.append(Ideia.status == status)
        if origem:
            filters.append(Ideia.origem == origem)

        if filters:
            query = query.where(and_(*filters))

        query = query.offset(skip).limit(limit).order_by(Ideia.criado_em.desc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update(self, ideia_id: UUID, ideia_data: IdeiaUpdate) -> Ideia | None:
        ideia = await self.get_by_id(ideia_id)
        if not ideia:
            return None

        update_data = ideia_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(ideia, field, value)

        await self.session.commit()
        await self.session.refresh(ideia)
        return ideia

    async def delete(self, ideia_id: UUID) -> bool:
        ideia = await self.get_by_id(ideia_id)
        if not ideia:
            return False

        await self.session.delete(ideia)
        await self.session.commit()
        return True

    async def update_embedding(self, ideia_id: UUID, embedding: list[float]) -> bool:
        ideia = await self.get_by_id(ideia_id)
        if not ideia:
            return False

        ideia.embedding = embedding
        await self.session.commit()
        return True

    async def find_similar(
        self,
        embedding: list[float],
        threshold: float,
        exclude_id: UUID | None = None,
        limit: int = 5,
    ) -> Sequence[Ideia]:
        """
        Busca ideias similares usando cosine distance.

        Args:
            embedding: Vetor de embedding para comparação
            threshold: Limiar de similaridade (0-1, onde 1 = idêntico)
            exclude_id: ID de ideia a excluir da busca
            limit: Número máximo de resultados

        Returns:
            Lista de ideias similares ordenadas por similaridade
        """
        from sqlalchemy import text

        # Usa cosine distance do pgvector
        # cosine distance = 1 - cosine similarity
        # Então threshold de 0.85 similarity = distance <= 0.15
        distance_threshold = 1 - threshold

        # Converte lista Python para formato de vetor PostgreSQL
        # Formato: [0.1,0.2,0.3,...] (sem espaços após vírgulas)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        # Constrói a condição de exclusão
        exclude_condition = ""
        if exclude_id is not None:
            exclude_condition = f"AND id != '{exclude_id}'::uuid"

        # Usa f-string para embutir o vetor diretamente na query
        # Isso evita problemas com parâmetros repetidos no asyncpg
        query = text(f"""
            SELECT id, nicho_id, origem, titulo, descricao_breve, status,
                   eh_continuacao_de, numero_parte, fonte_trend_id,
                   justificativa_llm, criado_em, atualizado_em, embedding,
                   1 - (embedding <=> '{embedding_str}'::vector) as similarity
            FROM ideias
            WHERE embedding IS NOT NULL
              AND (embedding <=> '{embedding_str}'::vector) <= {distance_threshold}
              {exclude_condition}
            ORDER BY embedding <=> '{embedding_str}'::vector
            LIMIT {limit}
        """)

        result = await self.session.execute(query)

        # Mapeia resultados para objetos Ideia
        ideias = []
        for row in result:
            ideia = Ideia(
                id=row.id,
                nicho_id=row.nicho_id,
                origem=row.origem,
                titulo=row.titulo,
                descricao_breve=row.descricao_breve,
                status=row.status,
                eh_continuacao_de=row.eh_continuacao_de,
                numero_parte=row.numero_parte,
                fonte_trend_id=row.fonte_trend_id,
                justificativa_llm=row.justificativa_llm,
                criado_em=row.criado_em,
                atualizado_em=row.atualizado_em,
                embedding=row.embedding,
            )
            ideias.append(ideia)

        return ideias
