"""
Repositório assíncrono para a entidade Roteiro.
"""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.roteiro import Roteiro
from app.schemas.roteiro import RoteiroCreate, RoteiroUpdate


class RoteiroRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, roteiro_data: RoteiroCreate) -> Roteiro:
        roteiro = Roteiro(**roteiro_data.model_dump(mode="json"))
        self.session.add(roteiro)
        await self.session.flush()
        created = await self.get_by_id(roteiro.id)
        assert created is not None
        return created

    async def get_by_id(self, roteiro_id: UUID) -> Roteiro | None:
        result = await self.session.execute(
            select(Roteiro)
            .options(selectinload(Roteiro.ideia))
            .where(Roteiro.id == roteiro_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        ideia_id: UUID | None = None,
        status: str | None = None,
    ) -> Sequence[Roteiro]:
        query = select(Roteiro).options(selectinload(Roteiro.ideia))

        filters = []
        if ideia_id:
            filters.append(Roteiro.ideia_id == ideia_id)
        if status:
            filters.append(Roteiro.status == status)

        if filters:
            query = query.where(and_(*filters))

        query = query.offset(skip).limit(limit).order_by(Roteiro.criado_em.desc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update(
        self, roteiro_id: UUID, roteiro_data: RoteiroUpdate
    ) -> Roteiro | None:
        roteiro = await self.get_by_id(roteiro_id)
        if not roteiro:
            return None

        update_data = roteiro_data.model_dump(exclude_unset=True, mode="json")
        for field, value in update_data.items():
            setattr(roteiro, field, value)

        await self.session.flush()
        updated = await self.get_by_id(roteiro.id)
        assert updated is not None
        return updated

    async def delete(self, roteiro_id: UUID) -> bool:
        roteiro = await self.get_by_id(roteiro_id)
        if not roteiro:
            return False

        await self.session.delete(roteiro)
        await self.session.flush()
        return True

    async def get_latest_version_by_ideia(self, ideia_id: UUID) -> Roteiro | None:
        result = await self.session.execute(
            select(Roteiro)
            .options(selectinload(Roteiro.ideia))
            .where(Roteiro.ideia_id == ideia_id)
            .order_by(Roteiro.versao.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_version_number_for_update(self, ideia_id: UUID) -> int:
        """Serialize revision allocation on the parent idea row."""

        from app.models.ideia import Ideia

        await self.session.execute(select(Ideia.id).where(Ideia.id == ideia_id).with_for_update())
        result = await self.session.execute(
            select(Roteiro.versao)
            .where(Roteiro.ideia_id == ideia_id)
            .order_by(Roteiro.versao.desc())
            .limit(1)
        )
        return result.scalar_one_or_none() or 0
