"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://lexiro:lexiro_dev@localhost:5432/lexiro"

    api_key: str = "ipx_dev_key_12345"

    embedding_model_gemini: str = "gemini-embedding-2-preview"
    embedding_dims: int = 1024
    embedding_cache_enabled: bool = True
    embedding_cache_ttl_hours: int = 48

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "lexiro"
    s3_secret_key: str = "lexiro_dev"
    s3_bucket: str = "lexiro-storage"

    database_url_sync: str = "postgresql://lexiro:lexiro_dev@localhost:5432/lexiro"

    max_upload_size_mb: int = 50
    max_archive_size_mb: int = 350

    tus_max_file_size_gb: int = 5
    tus_upload_ttl_hours: int = 24
    storage_quota_gb: int = 50
    product_quota_gb: int = 10

    reindex_heartbeat_interval_sec: int = 10
    reindex_stale_timeout_sec: int = 300
    reindex_doc_timeout_sec: int = 600

    llm_provider: str = "openai"  # "ollama" or "openai" (OpenAI-compatible: Gemini, GPT, etc.)
    ollama_url: str = "http://ollama:11434"
    llm_model: str = "qwen2.5-coder:7b"
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.2
    llm_timeout: int = 600
    llm_max_continuations: int = 3

    openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_api_key: str = ""
    openai_llm_model: str = "gemini-2.5-pro"

    llm_reasoning_effort: str = "low"  # "none" | "low" | "medium" | "high" (Gemini thinking budget)

    classifier_enabled: bool = True
    classifier_model: str = "gemini-2.5-flash"

    rag_top_k: int = 10
    rag_min_similarity: float = 0.35
    rag_history_messages: int = 6
    rag_history_max_tokens: int = 8000

    summary_enabled: bool = True
    summary_threshold: int = 8
    summary_model: str = "gemini-2.5-flash"
    summary_max_tokens: int = 500

    rerank_enabled: bool = True
    rerank_candidates: int = 20
    rerank_model: str = "gemini-2.5-flash"
    rerank_min_score: float = 0.3

    hybrid_search_enabled: bool = True
    hybrid_bm25_weight: float = 0.3
    hybrid_vector_weight: float = 0.7
    hybrid_rrf_k: int = 60
    hnsw_ef_search: int = 128

    doc_type_boost_enabled: bool = True

    multilang_bm25_enabled: bool = True

    chunk_max_tokens: int = 512
    chunk_min_tokens: int = 50
    chunk_overlap_paragraphs: int = 2
    embedding_max_tokens: int = 0  # 0 = auto (chunk_max_tokens + 256)

    metadata_extraction_enabled: bool = True
    metadata_extraction_model: str = "gemini-2.5-flash"
    metadata_extraction_batch_size: int = 5

    product_keys_extraction_enabled: bool = True
    product_resolve_model: str = "gemini-2.5-flash"

    search_retry_enabled: bool = True

    decompose_enabled: bool = True
    decompose_model: str = "gemini-2.5-flash"
    decompose_max_sub_queries: int = 4

    cross_doc_expansion_enabled: bool = True
    cross_doc_expansion_limit: int = 3

    web_search_enabled: bool = True
    web_search_model: str = "gemini-2.5-flash"
    web_search_max_tokens: int = 1500
    web_search_max_context_chars: int = 5000

    rag_max_context_tokens_per_source: int = 3000

    mcp_default_limit: int = 10

    model_max_input_tokens: int = 1_000_000

    ocr_enabled: bool = True
    ocr_lang_detect_model: str = "gemini-2.5-flash"
    ocr_vision_model: str = "gemini-2.5-flash"

    document_stale_timeout_sec: int = 900

    # --- Crawl defaults (shared across Confluence / Site / GitHub) ---
    crawl_max_pages: int = 10000
    crawl_max_depth: int = 100
    crawl_max_seconds: int = 7200

    # --- Per-type overrides (0 = use shared default above) ---
    confluence_crawl_max_pages: int = 0
    confluence_crawl_max_depth: int = 0
    confluence_crawl_max_seconds: int = 0

    site_crawl_max_pages: int = 0
    site_crawl_max_depth: int = 0
    site_crawl_max_seconds: int = 0

    # --- GitHub importer ---
    github_api_token: str = ""
    github_max_files: int = 0
    github_max_file_size_mb: int = 10

    # --- Auth ---
    api_key_hmac_secret: str = ""  # HMAC-SHA256 secret for API key hashing; empty = plain SHA-256 fallback
    jwt_secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 15
    jwt_refresh_token_days: int = 7

    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    oauth_enabled: bool = False  # master switch — disables all OAuth providers when False
    allowed_email_domain: str = "axxonsoft.dev"  # only emails ending with this domain can register; empty = no restriction

    app_base_url: str = "http://localhost:80"

    # --- Email (Resend) ---
    resend_api_key: str = ""
    email_from: str = "onboarding@resend.dev"

    # --- Sentry ---
    sentry_dsn: str = ""

    platform_name: str = "Lexiro"

    app_env: str = "development"
    app_log_level: str = "INFO"

    log_dir: str = "/app/logs"
    log_max_size_mb: int = 50
    log_retention_days: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
