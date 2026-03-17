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

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "ipcodex"
    s3_secret_key: str = "ipcodex_dev"
    s3_bucket: str = "ipcodex-storage"

    database_url_sync: str = "postgresql://ipcodex:ipcodex_dev@localhost:5432/ipcodex"

    max_upload_size_mb: int = 50

    ocr_enabled: bool = False
    ocr_languages: str = "en"

    app_env: str = "development"
    app_log_level: str = "INFO"

    log_dir: str = "/app/logs"
    log_max_size_mb: int = 50
    log_retention_days: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
