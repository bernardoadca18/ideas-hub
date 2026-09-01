"""
Configuração central via variáveis de ambiente (pydantic-settings).
Todos os parâmetros que precisam ser ajustados empiricamente (threshold de
similaridade, quantidade de ideias por trend etc.) ficam aqui, lidos do .env.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Banco
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ideas_hub"
    )

    # API
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # LLM / Agentes. Values are semantic 9Router combo/alias names; provider
    # composition and fallback remain entirely inside the gateway.
    llm_fast_model: str = "neovids-fast"
    llm_standard_model: str = "neovids-standard"
    llm_strong_model: str = "neovids-strong"
    llm_vision_model: str = "neovids-vision"
    llm_connect_timeout_seconds: float = 10.0
    llm_read_timeout_seconds: float = 180.0
    llm_max_attempts: int = 3
    llm_max_input_chars: int = 120_000
    tavily_api_key: str = ""
    tavily_connect_timeout_seconds: float = 5.0
    tavily_read_timeout_seconds: float = 20.0
    tavily_max_attempts: int = 2
    generation_research_max_queries: int = 4
    generation_research_results_per_query: int = 5
    generation_capacity_min_ratio: float = 0.55
    generation_capacity_additional_queries: int = 1

    # Embeddings
    embedding_provider: str = "ninerouter"
    embedding_model: str = "neovids-embedding"
    embedding_dim: int = 1024

    # 9Router OpenAI-compatible boundary. This is deliberately a service base
    # URL without /v1; callers own the endpoint suffix exactly once.
    ninerouter_base_url: str = "http://9router:20128"
    ninerouter_api_key: str = ""

    # Media Indexer (audiovisual memory service)
    media_indexer_base_url: str = "http://localhost:8012"
    media_indexer_timeout_seconds: int = 30
    media_indexer_api_key: str = (
        ""  # Optional, if Media Indexer requires authentication
    )

    # Game Analysis media context budget
    game_analysis_media_context_max_chars: int = 50000

    # Duration calibration is supplied by Orchestrator telemetry. The fallback is
    # explicit and versioned so Ideas Hub never needs to call a TTS provider.
    orchestrator_base_url: str = "http://localhost:8011"
    orchestrator_timeout_seconds: int = 5
    duration_fallback_words_per_minute: float = 145.0
    duration_fallback_chars_per_second: float = 14.5
    duration_revision_max_iterations: int = 2

    # Editorial generation. Thresholds are policy, not model/provider names.
    generation_single_pass_max_seconds: int = 480
    generation_staged_max_seconds: int = 2_700
    generation_section_target_seconds: int = 300
    generation_chapter_target_seconds: int = 1_800
    generation_max_sections: int = 120
    generation_max_calls: int = 180
    generation_max_revisions_per_section: int = 2
    generation_stale_after_seconds: int = 300
    generation_worker_poll_seconds: float = 2.0

    @property
    def resolved_llm_fast_model(self) -> str:
        return self.llm_fast_model

    @property
    def resolved_llm_standard_model(self) -> str:
        return self.llm_standard_model

    @property
    def resolved_llm_strong_model(self) -> str:
        return self.llm_strong_model

    @field_validator("ninerouter_base_url")
    @classmethod
    def validate_ninerouter_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if normalized.casefold().endswith("/v1"):
            raise ValueError("NINEROUTER_BASE_URL must not include the /v1 suffix")
        return normalized

    # Parâmetros ajustáveis
    ideia_similarity_threshold: float = 0.85
    ideias_por_trend: int = 3
    trends_max_por_fonte: int = 15

    # Fontes gratuitas
    youtube_api_key: str = ""
    reddit_public_user_agent: str = "ideas-hub/0.1"


settings = Settings()
