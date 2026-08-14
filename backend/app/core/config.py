"""
Configuração central via variáveis de ambiente (pydantic-settings).
Todos os parâmetros que precisam ser ajustados empiricamente (threshold de
similaridade, quantidade de ideias por trend etc.) ficam aqui, lidos do .env.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Banco
    database_url: str

    # API
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # LLM / Agentes
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    tavily_api_key: str = ""

    # Embeddings
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-large"
    embedding_dim: int = 1024

    # Parâmetros ajustáveis
    ideia_similarity_threshold: float = 0.85
    ideias_por_trend: int = 3
    trends_max_por_fonte: int = 15

    # Fontes gratuitas
    youtube_api_key: str = ""
    reddit_public_user_agent: str = "ideas-hub/0.1"


settings = Settings()
