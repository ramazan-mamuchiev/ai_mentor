export interface SourceInfo {
  doc_title: string
  heading_path: string
  similarity: number
  content_preview: string
  device_name: string
  firmware_version: string
}

export interface ChatMessage {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  sources?: SourceInfo[] | null
  duration_ms?: number | null
  created_at: string
}

export interface ChatSession {
  id: number
  title: string | null
  device_filter: string | null
  version_filter: string | null
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview?: string | null
}

export interface SessionDetail {
  id: number
  title: string | null
  device_filter: string | null
  version_filter: string | null
  created_at: string
  updated_at: string
  messages: ChatMessage[]
}

export type SSEEvent =
  | { type: 'token'; content: string }
  | { type: 'sources'; sources: SourceInfo[] }
  | { type: 'done'; message_id: number; duration_ms: number }
  | { type: 'error'; content: string }

export type StreamStatus = 'idle' | 'streaming' | 'error'
