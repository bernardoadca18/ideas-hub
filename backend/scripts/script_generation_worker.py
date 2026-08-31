"""Bounded DB-backed worker for resumable staged script generation."""

from __future__ import annotations

import asyncio
import signal

import structlog
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.external_research import external_research_client
from app.services.llm_gateway import llm_gateway
from app.services.script_generation_jobs import ScriptGenerationJobService

logger = structlog.get_logger("script_generation_worker")


async def run() -> None:
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stopping.set)
    try:
        while not stopping.is_set():
            async with AsyncSessionLocal() as session:
                service = ScriptGenerationJobService(session)
                claimed = await service.claim_next()
                if claimed is not None:
                    run_id = claimed.id
                    await session.commit()
                    logger.info("generation_run_claimed", run_id=str(run_id))
                    await service.process(run_id)
                    continue
            try:
                await asyncio.wait_for(
                    stopping.wait(), timeout=settings.generation_worker_poll_seconds
                )
            except TimeoutError:
                pass
    finally:
        await external_research_client.close()
        await llm_gateway.close()


if __name__ == "__main__":
    asyncio.run(run())
