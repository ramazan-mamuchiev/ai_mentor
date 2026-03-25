"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://ipcodex:ipcodex_dev@localhost:5432/ipcodex"

    api_key: str = "ipx_dev_key_12345"

    embedding_model_gemini: str = "gemini-embedding-2-preview"
    embedding_dims: int = 1024

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
    storage_quota_gb: int = 50
    product_quota_gb: int = 10

    reindex_heartbeat_interval_sec: int = 10
    reindex_stale_timeout_sec: int = 300
    reindex_doc_timeout_sec: int = 600

    llm_provider: str = "gemini"  # "ollama", "gemini" (OpenAI-compatible), or "bothub"
    ollama_url: str = "http://ollama:11434"
    llm_model: str = "qwen2.5-coder:7b"
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.2
    llm_timeout: int = 600
    llm_max_continuations: int = 3

    # === Gemini (OpenAI-compatible) ===
    openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_api_key: str = ""
    openai_llm_model: str = "gemini-2.5-pro"

    # === BotHub ===
    bothub_api_key: str = ""
    bothub_base_url: str = "https://bothub.chat/api/v2/openai/v1"
    bothub_llm_model: str = "gpt-4.5-turbo"

    llm_reasoning_effort: str = "low"  # "none" | "low" | "medium" | "high" (Gemini thinking budget)

    classifier_enabled: bool = True
    classifier_model: str = "gemini-2.5-flash"

    rag_top_k: int = 10
    rag_min_similarity: float = 0.35
    rag_history_messages: int = 6
    rag_history_max_tokens: int = 8000

    rerank_enabled: bool = True
    rerank_candidates: int = 20
    rerank_model: str = "gemini-2.5-flash"

    hybrid_search_enabled: bool = True
    hybrid_bm25_weight: float = 0.3
    hybrid_vector_weight: float = 0.7
    hybrid_rrf_k: int = 60

    chunk_max_tokens: int = 380
    chunk_min_tokens: int = 30
    chunk_overlap_paragraphs: int = 2

    metadata_extraction_enabled: bool = True
    metadata_extraction_model: str = "gemini-2.5-flash"
    metadata_extraction_batch_size: int = 5

    search_retry_enabled: bool = True

    ocr_enabled: bool = True
    ocr_lang_detect_model: str = "gemini-2.5-flash"

    app_env: str = "development"
    app_log_level: str = "INFO"

    log_dir: str = "/app/logs"
    log_max_size_mb: int = 50
    log_retention_days: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
