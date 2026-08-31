"""
Repositório assíncrono para a entidade Ideia.
"""

from __future__ import annotations

import builtins
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ideia import Ideia
from app.schemas.ideia import IdeiaCreate, IdeiaUpdate


@dataclass(frozen=True)
class SimilarIdeaMatch:
    idea: Ideia
    similarity: float


class IdeiaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, ideia_data: IdeiaCreate) -> Ideia:
        ideia = Ideia(**ideia_data.model_dump())
        self.session.add(ideia)
        await self.session.flush()
        created = await self.get_by_id(ideia.id)
        assert created is not None
        return created

    async def get_by_id(self, ideia_id: UUID) -> Ideia | None:
        result = await self.session.execute(
            select(Ideia).options(selectinload(Ideia.nicho)).where(Ideia.id == ideia_id)
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
        query = select(Ideia).options(selectinload(Ideia.nicho))

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

        await self.session.flush()
        updated = await self.get_by_id(ideia.id)
        assert updated is not None
        return updated

    async def delete(self, ideia_id: UUID) -> bool:
        ideia = await self.get_by_id(ideia_id)
        if not ideia:
            return False

        await self.session.delete(ideia)
        await self.session.flush()
        return True

    async def update_embedding(
        self, ideia_id: UUID, embedding: builtins.list[float]
    ) -> bool:
        ideia = await self.get_by_id(ideia_id)
        if not ideia:
            return False

        ideia.embedding = embedding
        await self.session.flush()
        return True

    async def find_similar(
        self,
        embedding: builtins.list[float],
        threshold: float,
        exclude_id: UUID | None = None,
        limit: int = 5,
    ) -> Sequence[SimilarIdeaMatch]:
        """
        Busca ideias similares usando cosine distance.

        Args:
            embedding: Vetor de embedding para comparação
            threshold: Limiar de similaridade (0-1, onde 1 = idêntico)
            exclude_id: ID de ideia a excluir da busca
            limit: Número máximo de resultados

        Returns:
            Matches tipados, ordenados por similaridade real decrescente.
        """
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        distance = Ideia.embedding.cosine_distance(embedding)
        similarity = (1 - distance).label("similarity")
        query = (
            select(Ideia, similarity)
            .options(selectinload(Ideia.nicho))
            .where(
                Ideia.embedding.isnot(None),
                distance <= 1 - threshold,
            )
        )
        if exclude_id is not None:
            query = query.where(Ideia.id != exclude_id)
        rows = await self.session.execute(query.order_by(distance).limit(limit))
        return [
            SimilarIdeaMatch(idea=idea, similarity=float(score))
            for idea, score in rows.all()
        ]
