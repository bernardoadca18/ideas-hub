"""
Repositório assíncrono para a entidade FonteTrendNicho.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fonte_trend_nicho import FonteTrendNicho
from app.schemas.fonte_trend_nicho import FonteTrendNichoCreate, FonteTrendNichoUpdate


class FonteTrendNichoRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, fonte_data: FonteTrendNichoCreate) -> FonteTrendNicho:
        fonte = FonteTrendNicho(**fonte_data.model_dump())
        self.session.add(fonte)
        await self.session.flush()
        await self.session.refresh(fonte)
        return fonte

    async def get_by_id(self, fonte_id: UUID) -> FonteTrendNicho | None:
        result = await self.session.execute(
            select(FonteTrendNicho).where(FonteTrendNicho.id == fonte_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        nicho_id: UUID | None = None,
        tipo: str | None = None,
        ativo: bool | None = None,
    ) -> Sequence[FonteTrendNicho]:
        query = select(FonteTrendNicho)

        filters = []
        if nicho_id:
            filters.append(FonteTrendNicho.nicho_id == nicho_id)
        if tipo:
            filters.append(FonteTrendNicho.tipo == tipo)
        if ativo is not None:
            filters.append(FonteTrendNicho.ativo == ativo)

        if filters:
            query = query.where(and_(*filters))

        query = (
            query.offset(skip).limit(limit).order_by(FonteTrendNicho.criado_em.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update(
        self, fonte_id: UUID, fonte_data: FonteTrendNichoUpdate
    ) -> FonteTrendNicho | None:
        fonte = await self.get_by_id(fonte_id)
        if not fonte:
            return None

        update_data = fonte_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(fonte, field, value)

        await self.session.flush()
        await self.session.refresh(fonte)
        return fonte

    async def delete(self, fonte_id: UUID) -> bool:
        fonte = await self.get_by_id(fonte_id)
        if not fonte:
            return False

        await self.session.delete(fonte)
        await self.session.flush()
        return True

    async def list_by_nicho(
        self, nicho_id: UUID, ativo: bool | None = None
    ) -> Sequence[FonteTrendNicho]:
        """Lista todas as fontes de um nicho específico."""
        return await self.list(nicho_id=nicho_id, ativo=ativo, limit=1000)
