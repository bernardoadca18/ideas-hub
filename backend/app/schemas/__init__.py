"""
Exports de todos os schemas.
"""

from app.schemas.fonte_trend_nicho import (
    FonteTrendNichoCreate,
    FonteTrendNichoResponse,
    FonteTrendNichoUpdate,
)
from app.schemas.ideia import IdeiaCreate, IdeiaResponse, IdeiaUpdate
from app.schemas.nicho import NichoCreate, NichoResponse, NichoUpdate
from app.schemas.roteiro import RoteiroCreate, RoteiroResponse, RoteiroUpdate
from app.schemas.trend_coletada import (
    TrendColetadaCreate,
    TrendColetadaResponse,
    TrendColetadaUpdate,
)

__all__ = [
    "FonteTrendNichoCreate",
    "FonteTrendNichoResponse",
    "FonteTrendNichoUpdate",
    "IdeiaCreate",
    "IdeiaResponse",
    "IdeiaUpdate",
    "NichoCreate",
    "NichoResponse",
    "NichoUpdate",
    "RoteiroCreate",
    "RoteiroResponse",
    "RoteiroUpdate",
    "TrendColetadaCreate",
    "TrendColetadaResponse",
    "TrendColetadaUpdate",
]
