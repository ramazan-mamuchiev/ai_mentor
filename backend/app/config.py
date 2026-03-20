"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://ipcodex:ipcodex_dev@localhost:5432/ipcodex"

    api_key: str = "ipx_dev_key_12345"

    embedding_provider: str = "local"  # "local" or "openai"
    embedding_model_local: str = "intfloat/multilingual-e5-large"
    embedding_model_openai: str = "text-embedding-3-small"
    embedding_dims: int = 1024
    openai_api_key: str = ""

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "ipcodex"
    s3_secret_key: str = "ipcodex_dev"
    s3_bucket: str = "ipcodex-storage"

    database_url_sync: str = "postgresql://ipcodex:ipcodex_dev@localhost:5432/ipcodex"

    max_upload_size_mb: int = 50
    max_archive_size_mb: int = 350

    tus_max_file_size_gb: int = 5
    tus_upload_ttl_hours: int = 24

    reindex_heartbeat_interval_sec: int = 10
    reindex_stale_timeout_sec: int = 300
    reindex_doc_timeout_sec: int = 600

    llm_provider: str = "openai"  # "ollama" or "openai" (OpenAI-compatible: Gemini, GPT, etc.)
    ollama_url: str = "http://ollama:11434"
    llm_model: str = "qwen2.5-coder:7b"
    llm_max_tokens: int = 16384
    llm_temperature: float = 0.2
    llm_timeout: int = 600
    llm_max_continuations: int = 3

    openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    openai_llm_api_key: str = ""
    openai_llm_model: str = "gemini-2.5-flash"

    rag_top_k: int = 15
    rag_history_messages: int = 10

    ocr_enabled: bool = False
    ocr_languages: str = "en"

    app_env: str = "development"
    app_log_level: str = "INFO"

    log_dir: str = "/app/logs"
    log_max_size_mb: int = 50
    log_retention_days: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
