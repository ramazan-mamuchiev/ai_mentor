export interface SourceInfo {
  doc_title: string
  heading_path: string
  similarity: number
  content_preview: string
  product_name: string
  firmware_version: string
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
  context_tokens: number
  history_tokens: number
  system_prompt_tokens: number
  user_input_tokens: number
  user_output_tokens: number
  llm_prompt_tokens: number
  llm_completion_tokens: number
  llm_total_tokens: number
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
  | { type: 'done'; message_id: number; duration_ms: number; debug?: DebugInfo }
  | { type: 'error'; error_code: string; status_code?: number }

export type StreamStatus = 'idle' | 'streaming' | 'error'
