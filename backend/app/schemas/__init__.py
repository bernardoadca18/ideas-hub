"""
Exports de todos os schemas.
"""
from app.schemas.nicho import NichoCreate, NichoUpdate, NichoResponse
from app.schemas.fonte_trend_nicho import (
    FonteTrendNichoCreate,
    FonteTrendNichoUpdate,
    FonteTrendNichoResponse,
)
from app.schemas.trend_coletada import (
    TrendColetadaCreate,
    TrendColetadaUpdate,
    TrendColetadaResponse,
)
from app.schemas.ideia import IdeiaCreate, IdeiaUpdate, IdeiaResponse
from app.schemas.roteiro import RoteiroCreate, RoteiroUpdate, RoteiroResponse

__all__ = [
    "NichoCreate",
    "NichoUpdate",
    "NichoResponse",
    "FonteTrendNichoCreate",
    "FonteTrendNichoUpdate",
    "FonteTrendNichoResponse",
    "TrendColetadaCreate",
    "TrendColetadaUpdate",
    "TrendColetadaResponse",
    "IdeiaCreate",
    "IdeiaUpdate",
    "IdeiaResponse",
    "RoteiroCreate",
    "RoteiroUpdate",
    "RoteiroResponse",
]
