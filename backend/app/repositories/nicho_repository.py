"""
Repositório assíncrono para a entidade Nicho.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nicho import Nicho
from app.schemas.nicho import NichoCreate, NichoUpdate


class NichoRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, nicho_data: NichoCreate) -> Nicho:
        nicho = Nicho(**nicho_data.model_dump())
        self.session.add(nicho)
        await self.session.flush()
        await self.session.refresh(nicho)
        return nicho

    async def get_by_id(self, nicho_id: UUID) -> Nicho | None:
        result = await self.session.execute(select(Nicho).where(Nicho.id == nicho_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Nicho | None:
        result = await self.session.execute(select(Nicho).where(Nicho.slug == slug))
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        ativo: bool | None = None,
    ) -> Sequence[Nicho]:
        query = select(Nicho)

        if ativo is not None:
            query = query.where(Nicho.ativo == ativo)

        query = query.offset(skip).limit(limit).order_by(Nicho.criado_em.desc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update(self, nicho_id: UUID, nicho_data: NichoUpdate) -> Nicho | None:
        nicho = await self.get_by_id(nicho_id)
        if not nicho:
            return None

        update_data = nicho_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(nicho, field, value)

        await self.session.flush()
        await self.session.refresh(nicho)
        return nicho

    async def delete(self, nicho_id: UUID) -> bool:
        nicho = await self.get_by_id(nicho_id)
        if not nicho:
            return False

        await self.session.delete(nicho)
        await self.session.flush()
        return True
