from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.database import get_db


def session_context(session: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


@pytest.mark.asyncio
async def test_request_unit_of_work_commits_once_after_success() -> None:
    session = AsyncMock()
    with patch(
        "app.core.database.AsyncSessionLocal", return_value=session_context(session)
    ):
        dependency = get_db()
        assert await anext(dependency) is session
        with pytest.raises(StopAsyncIteration):
            await anext(dependency)

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_unit_of_work_rolls_back_after_failure() -> None:
    session = AsyncMock()
    with patch(
        "app.core.database.AsyncSessionLocal", return_value=session_context(session)
    ):
        dependency = get_db()
        assert await anext(dependency) is session
        with pytest.raises(RuntimeError, match="business failure"):
            await dependency.athrow(RuntimeError("business failure"))

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
