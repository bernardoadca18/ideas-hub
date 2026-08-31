"""
Repositório assíncrono para a entidade TrendColetada.
"""

from __future__ import annotations

import builtins
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trend_coletada import TrendColetada
from app.schemas.trend_coletada import TrendColetadaCreate, TrendColetadaUpdate


class TrendColetadaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, trend_data: TrendColetadaCreate) -> TrendColetada:
        trend = TrendColetada(**trend_data.model_dump())
        self.session.add(trend)
        await self.session.flush()
        await self.session.refresh(trend)
        return trend

    async def get_by_id(self, trend_id: UUID) -> TrendColetada | None:
        result = await self.session.execute(
            select(TrendColetada).where(TrendColetada.id == trend_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        nicho_id: UUID | None = None,
        status: str | None = None,
        fonte: str | None = None,
    ) -> Sequence[TrendColetada]:
        query = select(TrendColetada)

        filters = []
        if nicho_id:
            filters.append(TrendColetada.nicho_id == nicho_id)
        if status:
            filters.append(TrendColetada.status == status)
        if fonte:
            filters.append(TrendColetada.fonte == fonte)

        if filters:
            query = query.where(and_(*filters))

        query = (
            query.offset(skip).limit(limit).order_by(TrendColetada.coletado_em.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update(
        self, trend_id: UUID, trend_data: TrendColetadaUpdate
    ) -> TrendColetada | None:
        trend = await self.get_by_id(trend_id)
        if not trend:
            return None

        update_data = trend_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(trend, field, value)

        await self.session.flush()
        await self.session.refresh(trend)
        return trend

    async def delete(self, trend_id: UUID) -> bool:
        trend = await self.get_by_id(trend_id)
        if not trend:
            return False

        await self.session.delete(trend)
        await self.session.flush()
        return True

    async def create_batch(
        self, trends_data: builtins.list[TrendColetadaCreate]
    ) -> builtins.list[TrendColetada]:
        trends = [TrendColetada(**data.model_dump()) for data in trends_data]
        self.session.add_all(trends)
        await self.session.flush()
        for trend in trends:
            await self.session.refresh(trend)
        return trends
