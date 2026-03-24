export interface SourceInfo {
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
  session_id: number
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
  prompt_hash?: string
  retry_used?: boolean
  rephrase_ms?: number
  rephrase_query?: string | null
  status?: 'success' | 'stopped' | 'error'
  status_detail?: string
}

export interface ChatMessage {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  sources?: SourceInfo[] | null
  duration_ms?: number | null
  debug?: DebugInfo | null
  error_code?: string | null
  created_at: string
}

export interface ChatSession {
  id: number
  title: string | null
  product_filter: string | null
  version_filter: string | null
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview?: string | null
}

export interface SessionDetail {
  id: number
  title: string | null
  product_filter: string | null
  version_filter: string | null
  created_at: string
  updated_at: string
  messages: ChatMessage[]
}

export type SSEEvent =
  | { type: 'token'; content: string }
  | { type: 'sources'; sources: SourceInfo[] }
  | { type: 'debug_partial'; debug: Partial<DebugInfo> }
  | { type: 'done'; message_id: number; duration_ms: number; debug?: DebugInfo; product_filter?: string | null; version_filter?: string | null; auto_product?: string | null }
  | { type: 'error'; error_code: string; status_code?: number; error_type?: string; detail?: string }

export type StreamStatus = 'idle' | 'streaming' | 'error'

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
  slug: string
  manufacturer_slug: string
  created_at: string
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
  slug: string
  manufacturer_slug: string
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
