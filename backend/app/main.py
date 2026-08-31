"""Entry point da API ideas-hub."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import setup_logging

# Configura logging estruturado
setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    from app.services.external_research import external_research_client
    from app.services.llm_gateway import llm_gateway

    await external_research_client.close()
    await llm_gateway.close()


app = FastAPI(title="ideas-hub", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _check_readiness(db: AsyncSession) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    return await _check_readiness(db)


@app.get("/health")
async def health(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Compatibility alias with readiness semantics."""

    return await _check_readiness(db)


# Routers
from app.api.routers import (
    fontes_trend,
    generation_runs,
    ideias,
    nichos,
    roteiros,
    trends,
)

app.include_router(nichos.router)
app.include_router(ideias.router)
app.include_router(trends.router)
app.include_router(roteiros.router)
app.include_router(fontes_trend.router)
app.include_router(generation_runs.router)
