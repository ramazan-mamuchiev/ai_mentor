"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://ipcodex:ipcodex_dev@localhost:5432/ipcodex"

    api_key: str = "ipx_dev_key_12345"

    embedding_provider: str = "local"  # "local" or "openai"
    embedding_model_local: str = "all-MiniLM-L6-v2"
    embedding_model_openai: str = "text-embedding-3-small"
    embedding_dims: int = 1536
    openai_api_key: str = ""

    app_env: str = "development"
    app_log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
