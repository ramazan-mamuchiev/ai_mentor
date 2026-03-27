"""Provider-aware credentials for LLM and embedding API calls.

Returns the correct (api_key, base_url) pair depending on
settings.llm_provider ("gemini" or "bothub").
"""

from app.config import settings


def llm_credentials() -> tuple[str, str]:
    """Return (api_key, base_url) for OpenAI-compatible LLM calls."""
    if settings.llm_provider == "bothub":
        return settings.bothub_api_key, settings.bothub_base_url
    return settings.gemini_api_key, settings.openai_base_url


def embedding_credentials() -> tuple[str, str, str]:
    """Return (api_key, base_url, model) for embedding calls."""
    if settings.llm_provider == "bothub":
        return (
            settings.bothub_api_key,
            settings.bothub_base_url,
            settings.bothub_embedding_model,
        )
    return (
        settings.gemini_api_key,
        settings.openai_base_url,
        settings.embedding_model_gemini,
    )
