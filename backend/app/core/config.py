"""
Configuração central via variáveis de ambiente (pydantic-settings).
Todos os parâmetros que precisam ser ajustados empiricamente (threshold de
similaridade, quantidade de ideias por trend etc.) ficam aqui, lidos do .env.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Banco
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ideas_hub"

    # API
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # LLM / Agentes
    llm_model: str = ""  # Modelo a ser usado via LiteLLM Proxy (ex: gpt-4o, gemini-pro)
    tavily_api_key: str = ""

    # Embeddings
    embedding_provider: str = "openai"
    embedding_model: str = "ollama-embed"
    embedding_dim: int = 1024

    # LiteLLM Proxy
    litellm_base_url: str = "http://172.20.0.1:4000"  # Endpoint do proxy local (gateway Docker)
    litellm_master_key: str = ""  # Chave mestra do proxy

    # Media Indexer (audiovisual memory service)
    media_indexer_base_url: str = "http://localhost:8012"
    media_indexer_timeout_seconds: int = 30
    media_indexer_api_key: str = ""  # Optional, if Media Indexer requires authentication

    # Game Analysis media context budget
    game_analysis_media_context_max_chars: int = 50000

    # Duration calibration is supplied by Orchestrator telemetry. The fallback is
    # explicit and versioned so Ideas Hub never needs to call a TTS provider.
    orchestrator_base_url: str = "http://localhost:8011"
    orchestrator_timeout_seconds: int = 5
    duration_fallback_words_per_minute: float = 145.0
    duration_fallback_chars_per_second: float = 14.5
    duration_revision_max_iterations: int = 2

    # Parâmetros ajustáveis
    ideia_similarity_threshold: float = 0.85
    ideias_por_trend: int = 3
    trends_max_por_fonte: int = 15

    # Fontes gratuitas
    youtube_api_key: str = ""
    reddit_public_user_agent: str = "ideas-hub/0.1"


settings = Settings()
