# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added

- **BotHub as universal LLM/embedding provider** — all backend components now support
  BotHub (`llm_provider=bothub`) as an alternative to direct Gemini API access.
  Previously only the chat streaming endpoint worked with BotHub; now embeddings,
  metadata extraction, reranking, query classification, query decomposition,
  history summarization, and OCR language detection all route through the
  configured provider.

- New helper module `backend/app/llm/credentials.py` with `llm_credentials()`
  and `embedding_credentials()` — returns the correct `(api_key, base_url)` pair
  based on `settings.llm_provider`.

- New config setting `BOTHUB_EMBEDDING_MODEL` (default: `text-embedding-3-large`) —
  controls which embedding model is used when provider is BotHub.

- OpenAI-compatible embedding path in `embedder.py` — uses standard
  `POST /embeddings` endpoint with `dimensions` parameter for BotHub/OpenRouter
  and similar providers.

### Changed

- `embedder.py` — refactored into two internal paths:
  - `_embed_via_gemini()` — original Google `genai` SDK path (unchanged behavior)
  - `_embed_via_openai_compatible()` — new httpx-based path for BotHub
  - Public API (`embed_texts`, `embed_query`) unchanged.

- `metadata_extractor.py` — `_call_llm_sync()` and `_call_llm_async()` now use
  `llm_credentials()` instead of hardcoded `gemini_api_key` / `openai_base_url`.
  Removed `reasoning_effort` parameter (not supported by all providers).

- `reranker.py` — `_call_rerank_api()` and `rerank()` now use `llm_credentials()`.
  API key check uses provider-aware credentials instead of `gemini_api_key` directly.

- `rag.py` — four internal LLM call sites updated to use `llm_credentials()`:
  - Query classifier (`classify_query`)
  - Query rewriter (`_llm_rewrite_openai`)
  - Query decomposer (`decompose_query`)
  - History summarizer (`summarize_history`)
  - Removed `reasoning_effort` parameter from these calls.

- `ocr.py` — `detect_language_via_gemini()` renamed to `detect_language_via_llm()`.
  Now supports both Gemini (native SDK) and BotHub (OpenAI-compatible HTTP).
  Callers in `pdf.py` and `confluence.py` updated accordingly.

- `docker-compose.yml` — added `BOTHUB_EMBEDDING_MODEL` env var to `api` and
  `worker` services.

- `.env.example` — added `BOTHUB_EMBEDDING_MODEL=text-embedding-3-large`.

### Fixed

- All auxiliary LLM calls (metadata extraction, reranking, classification, etc.)
  now work correctly when `llm_provider=bothub` — previously they failed with
  `Illegal header value b'Bearer '` because `gemini_api_key` was empty.

### Migration notes

- **Embedding model change**: switching from Gemini to BotHub changes the embedding
  model from `gemini-embedding-2-preview` to `text-embedding-3-large`. These produce
  incompatible vector spaces — **full document reindexing is required** after switching.

- **Environment variables**: when using BotHub, ensure `.env` contains:
  ```
  LLM_PROVIDER=bothub
  BOTHUB_API_KEY=your_key_here
  BOTHUB_BASE_URL=https://bothub.chat/api/v2/openai/v1
  ```
  `GEMINI_API_KEY` is no longer required when provider is `bothub`.

### Files changed

| File | Change |
|------|--------|
| `backend/app/llm/credentials.py` | **New** — provider-aware credential helpers |
| `backend/app/config.py` | Added `bothub_embedding_model` setting |
| `backend/app/ingestion/embedder.py` | Dual-provider embedding (Gemini SDK + OpenAI HTTP) |
| `backend/app/ingestion/metadata_extractor.py` | Use `llm_credentials()` |
| `backend/app/search/reranker.py` | Use `llm_credentials()` |
| `backend/app/chat/rag.py` | Use `llm_credentials()` in 4 call sites |
| `backend/app/ingestion/converters/ocr.py` | Renamed + dual-provider language detection |
| `backend/app/ingestion/converters/pdf.py` | Updated import |
| `backend/app/ingestion/converters/confluence.py` | Updated import |
| `docker-compose.yml` | Added `BOTHUB_EMBEDDING_MODEL` to api/worker |
| `.env.example` | Added `BOTHUB_EMBEDDING_MODEL` |
