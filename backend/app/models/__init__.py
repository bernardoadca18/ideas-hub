"""
Exports de todos os models.
"""
from app.models.base import Base, TimestampMixin
from app.models.nicho import Nicho
from app.models.fonte_trend_nicho import FonteTrendNicho
from app.models.trend_coletada import TrendColetada
from app.models.ideia import Ideia
from app.models.roteiro import Roteiro

__all__ = [
    "Base",
    "TimestampMixin",
    "Nicho",
    "FonteTrendNicho",
    "TrendColetada",
    "Ideia",
    "Roteiro",
]
