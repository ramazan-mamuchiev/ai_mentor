export interface SourceInfo {
  document_id?: number | null
  doc_title: string
  heading_path: string
  similarity: number
  content_preview: string
  product_name: string
  firmware_version: string
  doc_type?: string
  entities?: Record<string, string[]>
}

export interface DebugInfo {
  session_id: string
  message_id: number
  user_message_id: number
  timestamp: string
  model: string
  llm_provider: string
  temperature: number
  max_tokens: number
  first_token_ms: number
  rag_ms: number
  llm_ms: number
  total_ms: number
  token_count: number
  tokens_per_sec: number
  response_length: number
  chunks_found: number
  top_similarity: number
  min_similarity: number
  context_tokens: number
  search_ms: number
  rag_build_ms: number
  history_messages: number
  prompt_messages: number
  embedding_model: string
  product_filter: string | null
  version_filter: string | null
  doc_context: string | null
  auto_product: string | null
  detected_doc_context: string | null
  search_query: string | null
  query_tokens: number
  history_tokens: number
  system_prompt_tokens: number
  user_input_tokens: number
  user_output_tokens: number
  llm_prompt_tokens: number
  llm_completion_tokens: number
  llm_total_tokens: number
  rerank_prompt_tokens: number
  rerank_completion_tokens: number
  rerank_total_tokens: number
  rerank_model: string
  query_type?: string
  classify_model?: string
  classify_ms?: number
  classify_prompt_tokens?: number
  classify_completion_tokens?: number
  classify_total_tokens?: number
  classify_raw?: string
  classify_input?: string
  classify_product?: string | null
  prompt_hash?: string
  summary_model?: string
  summary_ms?: number
  summary_prompt_tokens?: number
  summary_completion_tokens?: number
  summary_total_tokens?: number
  finish_reason?: string
  continuations?: number
  effective_top_k?: number
  rewrite_prompt_tokens?: number
  rewrite_completion_tokens?: number
  rewrite_total_tokens?: number
  rewrite_model?: string
  embedding_api_tokens?: number
  retry_used?: boolean
  rephrase_ms?: number
  rephrase_query?: string | null
  rephrase_prompt_tokens?: number
  rephrase_completion_tokens?: number
  rephrase_total_tokens?: number
  rephrase_model?: string
  decompose_used?: boolean
  decompose_sub_queries?: string[]
  decompose_sub_products?: (string | null)[]
  decompose_model?: string
  decompose_ms?: number
  decompose_prompt_tokens?: number
  decompose_completion_tokens?: number
  decompose_total_tokens?: number
  web_search_used?: boolean
  web_search_model?: string
  web_search_ms?: number
  web_search_prompt_tokens?: number
  web_search_completion_tokens?: number
  web_search_total_tokens?: number
  web_search_queries?: string[]
  web_search_sources_count?: number
  web_search_sources?: { title: string; uri: string }[]
  web_search_context_length?: number
  status?: 'success' | 'stopped' | 'error'
  status_detail?: string
}

export interface ChatMessage {
  id: number
  session_id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceInfo[] | null
  duration_ms?: number | null
  feedback?: 'up' | 'down' | null
  feedback_comment?: string | null
  debug?: DebugInfo | null
  error_code?: string | null
  created_at: string
}

export interface ChatSession {
  id: string
  title: string | null
  product_id: number | null
  product_filter: string | null
  product_filter_source: string | null
  version_filter: string | null
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview?: string | null
}

export interface SessionDetail {
  id: string
  title: string | null
  product_id: number | null
  product_filter: string | null
  product_filter_source: string | null
  version_filter: string | null
  created_at: string
  updated_at: string
  messages: ChatMessage[]
}

export type SSEEvent =
  | { type: 'progress'; stage: string; sub_queries?: number }
  | { type: 'token'; content: string }
  | { type: 'sources'; sources: SourceInfo[] }
  | { type: 'debug_partial'; debug: Partial<DebugInfo> }
  | { type: 'done'; message_id: number; duration_ms: number; debug?: DebugInfo; product_filter?: string | null; product_filter_source?: string | null; version_filter?: string | null; auto_product?: string | null }
  | { type: 'error'; error_code: string; status_code?: number; error_type?: string; detail?: string }

export type StreamStatus = 'idle' | 'streaming' | 'error'

export interface SharedLinkResponse {
  token: string
  url: string
  share_type: string
  title: string
  view_count: number
  is_active: boolean
  created_at: string
  expires_at: string | null
}

export interface SharedMessageSnapshot {
  role: 'user' | 'assistant'
  content: string
  sources?: Record<string, unknown>[] | null
  created_at: string
}

export interface SharedContentResponse {
  share_type: 'session' | 'message'
  title: string
  product_filter: string | null
  version_filter: string | null
  messages: SharedMessageSnapshot[]
  created_at: string
  view_count: number
}

export interface SharedDebugContentResponse {
  share_type: string
  title: string
  data: Record<string, unknown>
  created_at: string
  view_count: number
  expires_at: string | null
}

export type DocumentStatusValue = 'pending' | 'processing' | 'ready' | 'error' | 'cancelled'

export interface DocumentListItem {
  id: number
  title: string
  format: string
  status: DocumentStatusValue
  original_filename: string
  file_size_bytes: number
  total_chunks: number
  product_name: string | null
  firmware_version: string | null
  error_message: string | null
  uploaded_at: string | null
  indexed_at: string | null
  progress_percent: number
  progress_stage: string
  detected_language: string | null
  source_container: string | null
  source_path: string | null
}

export interface DocumentDebugInfo {
  document_id: number
  title: string
  original_filename: string
  format: string
  status: string
  source_hash: string

  file_size_bytes: number
  uploaded_at: string
  indexed_at: string | null
  error_message: string | null

  ingest_duration_ms: number | null
  read_ms: number | null
  convert_ms: number | null
  parse_ms: number | null
  embed_ms: number | null
  db_ms: number | null

  total_chunks: number
  total_tokens: number
  min_chunk_tokens: number | null
  max_chunk_tokens: number | null
  avg_chunk_tokens: number | null

  embedding_model: string | null
  embedding_dims: number | null
  embedding_tokens: number

  rag_hit_count: number
  rag_avg_similarity: number | null
  rag_last_used_at: string | null

  ocr_ms: number | null
  ocr_images_total: number | null
  ocr_images_success: number | null
  ocr_images_empty: number | null
  ocr_images_failed: number | null
  ocr_prompt_tokens: number | null
  ocr_completion_tokens: number | null
  ocr_model: string | null
  detected_language: string | null

  extract_ms: number | null
  extract_model: string | null
  extract_prompt_tokens: number | null
  extract_completion_tokens: number | null

  product_name: string
  firmware_version: string
}

export interface DocumentDownload {
  document_id: number
  original_filename: string
  download_url: string
  expires_in_seconds: number
}

export interface DocumentMarkdownPreview {
  document_id: number
  title: string
  markdown: string
  size_bytes: number
  source: 's3_converted' | 's3_original' | 'chunks_reconstructed'
}

export interface FormatCount {
  format: string
  count: number
}

export interface ProductListItem {
  id: number
  name: string
  manufacturer: string
  model: string
  category: string
  created_at: string
  firmware_version_id: number | null
  version: string
  display_name: string
  total_documents: number
  pending_documents: number
  processing_documents: number
  ready_documents: number
  error_documents: number
  cancelled_documents: number
  total_file_size_bytes: number
  total_chunks: number
  formats: FormatCount[]
  uploaded_at: string | null
  indexed_at: string | null
  progress_percent: number
  progress_detail: string
}

export interface ProductDetail {
  id: number
  name: string
  manufacturer: string
  model: string
  category: string
  created_at: string
  firmware_versions: string[]
}

export interface ProductDocumentSummary {
  id: number
  title: string
  format: string
  file_size_bytes: number
  total_chunks: number
  status: string
  indexed_at: string | null
}

export interface ProductDebugInfo {
  product_id: number
  product_name: string
  total_documents: number
  firmware_version_count: number
  total_file_size_bytes: number
  sum_ingest_duration_ms: number | null
  avg_ingest_duration_ms: number | null
  sum_read_ms: number | null
  sum_convert_ms: number | null
  sum_parse_ms: number | null
  sum_embed_ms: number | null
  sum_db_ms: number | null
  total_chunks: number
  total_tokens: number
  min_chunk_tokens: number | null
  max_chunk_tokens: number | null
  avg_chunk_tokens: number | null
  embedding_model: string | null
  total_embedding_tokens: number
  total_rag_hit_count: number
  avg_rag_similarity: number | null
  last_rag_used_at: string | null
  sum_extract_ms: number | null
  total_extract_tokens: number
  documents: ProductDocumentSummary[]
}

export interface DocumentUsageEntry {
  created_at: string
  session_id: string
  message_id: number
  heading_path: string
  similarity: number
  context_tokens: number
  query_text: string | null
  query_type: string | null
  sub_query: string | null
  charge_usd: number
}

export interface DocumentUsageStats {
  document_id: number
  title: string
  total_usages: number
  unique_sessions: number
  total_context_tokens: number
  total_charge_usd: number
  avg_similarity: number | null
  first_used_at: string | null
  last_used_at: string | null
  thumbs_up: number
  thumbs_down: number
  total_rated: number
  top_headings: { heading_path: string; count: number }[]
  recent_usages: DocumentUsageEntry[]
}

export interface ProductDocumentUsage {
  document_id: number
  title: string
  total_usages: number
  total_context_tokens: number
  total_charge_usd: number
  avg_similarity: number | null
  last_used_at: string | null
  thumbs_up: number
  thumbs_down: number
}

export interface ProductUsageStats {
  product_id: number
  product_name: string
  total_usages: number
  unique_sessions: number
  unique_documents: number
  total_context_tokens: number
  total_charge_usd: number
  avg_similarity: number | null
  first_used_at: string | null
  last_used_at: string | null
  thumbs_up: number
  thumbs_down: number
  total_rated: number
  documents: ProductDocumentUsage[]
}

export interface SuggestionChip {
  text_en: string
  text_ru: string
  product_filter: string
}

export type ReindexMode = 'reingest' | 'reembed' | 'extract_metadata'
export type ReindexStatus = 'pending' | 'running' | 'completed' | 'cancelled' | 'failed'

export interface ReindexJob {
  id: number
  mode: ReindexMode
  status: ReindexStatus
  product_filter: string | null
  format_filter: string | null
  total_documents: number
  processed_documents: number
  failed_documents: number
  skipped_documents: number
  total_chunks: number
  progress_percent: number
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  is_stale: boolean
}

export interface ReindexJobList {
  jobs: ReindexJob[]
  total: number
}

export interface FirmwareVersionInfo {
  id: number
  version: string
}
