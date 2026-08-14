"""
Entry point da API ideas-hub.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(title="ideas-hub", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Routers
from app.api.routers import nichos, ideias, trends, roteiros

app.include_router(nichos.router)
app.include_router(ideias.router)
app.include_router(trends.router)
app.include_router(roteiros.router)
