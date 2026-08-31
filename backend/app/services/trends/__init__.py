"""
Serviços de coleta de trends.
"""

from app.services.trends.base import BaseTrendCollector, TrendColetada
from app.services.trends.coletor import TrendsCollectorService
from app.services.trends.google_trends import google_trends_collector
from app.services.trends.reddit_publico import reddit_publico_collector
from app.services.trends.rss import rss_collector
from app.services.trends.youtube import youtube_collector

__all__ = [
    "BaseTrendCollector",
    "TrendColetada",
    "TrendsCollectorService",
    "google_trends_collector",
    "reddit_publico_collector",
    "rss_collector",
    "youtube_collector",
]
