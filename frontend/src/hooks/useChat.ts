import { useCallback, useRef, useState } from 'react'
import i18n from '../i18n'
import { streamMessage } from '../api/chat'
import type { ChatMessage, DebugInfo, SourceInfo, StreamStatus } from '../types'

function snakeToCamel(s: string): string {
  return s.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
}

interface ProductUpdate {
  product_filter?: string | null
  product_filter_source?: string | null
  version_filter?: string | null
  auto_product?: string | null
}

interface UseChatOptions {
  onProductDetected?: (sessionId: number, update: ProductUpdate) => void
}

interface UseChatReturn {
  messages: ChatMessage[]
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  streamingContent: string
  streamingSources: SourceInfo[]
  streamingStage: string
  status: StreamStatus
  lastUserPrompt: string
  sendMessage: (sessionId: number, content: string) => Promise<void>
  cancel: () => void
  reset: () => void
  retryLast: (sessionId: number) => void
}

export function useChat(options?: UseChatOptions): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingSources, setStreamingSources] = useState<SourceInfo[]>([])
  const [streamingStage, setStreamingStage] = useState('')
  const [status, setStatus] = useState<StreamStatus>('idle')
  const [lastUserPrompt, setLastUserPrompt] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const contentRef = useRef('')
  const sourcesRef = useRef<SourceInfo[]>([])
  const lastPromptRef = useRef('')
  const streamStartRef = useRef(0)
  const partialDebugRef = useRef<Partial<DebugInfo> | null>(null)
  const stageRef = useRef('')

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null

    const partial = contentRef.current
    const partialSources = sourcesRef.current
    const elapsedMs = streamStartRef.current ? Date.now() - streamStartRef.current : 0
    if (partial) {
      const tokenCount = partial.split(/\s+/).length
      const serverDebug = partialDebugRef.current ?? {}
      const completionTokens = tokenCount
      const promptTokens = (serverDebug.llm_prompt_tokens as number) ?? 0

      const mergedDebug: DebugInfo = {
        ...serverDebug,
        total_ms: elapsedMs,
        token_count: completionTokens,
        response_length: partial.length,
        user_output_tokens: completionTokens,
        llm_completion_tokens: completionTokens,
        llm_total_tokens: promptTokens + completionTokens,
        status: 'stopped',
      } as DebugInfo

      const stoppedMsg: ChatMessage = {
        id: Date.now() + 1,
        session_id: (serverDebug.session_id as number) ?? 0,
        role: 'assistant',
        content: partial + '\n\n' + i18n.t('chat.stopped'),
        sources: partialSources.length > 0 ? partialSources : undefined,
        duration_ms: elapsedMs,
        debug: mergedDebug,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, stoppedMsg])
    }

    setStreamingContent('')
    setStreamingSources([])
    setStreamingStage('')
    setStatus('idle')
    setLastUserPrompt(lastPromptRef.current)
    contentRef.current = ''
    sourcesRef.current = []
    streamStartRef.current = 0
    partialDebugRef.current = null
    stageRef.current = ''
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setStreamingContent('')
    setStreamingSources([])
    setStreamingStage('')
    setStatus('idle')
    setLastUserPrompt('')
    contentRef.current = ''
    sourcesRef.current = []
    lastPromptRef.current = ''
    stageRef.current = ''
  }, [])

  const sendMessage = useCallback(async (sessionId: number, content: string) => {
    const userMsg: ChatMessage = {
      id: Date.now(),
      session_id: sessionId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setStreamingContent('')
    setStreamingSources([])
    setStreamingStage('')
    setStatus('streaming')
    setLastUserPrompt('')
    contentRef.current = ''
    sourcesRef.current = []
    stageRef.current = ''
    lastPromptRef.current = content

    const controller = new AbortController()
    abortRef.current = controller
    streamStartRef.current = Date.now()
    partialDebugRef.current = null

    try {
      let fullContent = ''
      let sources: SourceInfo[] = []
      let msgId = 0
      let durationMs = 0
      let debugInfo: DebugInfo | null = null
      let tokenCount = 0

      for await (const event of streamMessage(sessionId, content, controller.signal)) {
        switch (event.type) {
          case 'progress':
            stageRef.current = event.stage
            setStreamingStage(event.stage)
            break
          case 'token':
            if (stageRef.current) {
              stageRef.current = ''
              setStreamingStage('')
            }
            fullContent += event.content
            tokenCount++
            contentRef.current = fullContent
            setStreamingContent(fullContent)
            break
          case 'sources':
            sources = event.sources
            sourcesRef.current = sources
            setStreamingSources(sources)
            break
          case 'debug_partial':
            partialDebugRef.current = event.debug as Partial<DebugInfo>
            break
          case 'done':
            msgId = event.message_id
            durationMs = event.duration_ms
            debugInfo = event.debug ?? null
            if (options?.onProductDetected && (event.auto_product || event.product_filter)) {
              options.onProductDetected(sessionId, {
                product_filter: event.product_filter,
                product_filter_source: event.product_filter_source,
                version_filter: event.version_filter,
                auto_product: event.auto_product,
              })
            }
            break
          case 'error': {
            const errCode = snakeToCamel(event.error_code || 'internal_error')
            const elapsedErr = streamStartRef.current ? Date.now() - streamStartRef.current : 0
            const errServerDebug = partialDebugRef.current ?? {}
            const errorDetail = [event.error_type, event.detail].filter(Boolean).join(': ') || errCode
            const errorMsg: ChatMessage = {
              id: Date.now() + 1,
              session_id: sessionId,
              role: 'assistant',
              content: '',
              error_code: errCode,
              duration_ms: elapsedErr,
              debug: {
                ...errServerDebug,
                total_ms: elapsedErr,
                status: 'error',
                status_detail: errorDetail,
              } as DebugInfo,
              created_at: new Date().toISOString(),
            }
            setMessages(prev => [...prev, errorMsg])
            setStreamingContent('')
            setStreamingSources([])
            setStreamingStage('')
            setStatus('idle')
            setLastUserPrompt(lastPromptRef.current)
            contentRef.current = ''
            sourcesRef.current = []
            stageRef.current = ''
            streamStartRef.current = 0
            partialDebugRef.current = null
            return
          }
        }
      }

      const assistantMsg: ChatMessage = {
        id: msgId || Date.now() + 1,
        session_id: sessionId,
        role: 'assistant',
        content: fullContent,
        sources,
        duration_ms: durationMs,
        debug: debugInfo,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, assistantMsg])
      setStreamingContent('')
      setStreamingSources([])
      setStreamingStage('')
      setStatus('idle')
      contentRef.current = ''
      sourcesRef.current = []
      stageRef.current = ''
      streamStartRef.current = 0
      partialDebugRef.current = null
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        const elapsedNet = streamStartRef.current ? Date.now() - streamStartRef.current : 0
        const netServerDebug = partialDebugRef.current ?? {}
        const errorMsg: ChatMessage = {
          id: Date.now() + 1,
          session_id: sessionId,
          role: 'assistant',
          content: '',
          error_code: 'networkError',
          duration_ms: elapsedNet,
          debug: {
            ...netServerDebug,
            total_ms: elapsedNet,
            status: 'error',
            status_detail: 'networkError',
          } as DebugInfo,
          created_at: new Date().toISOString(),
        }
        setMessages(prev => [...prev, errorMsg])
        setStreamingContent('')
        setStreamingSources([])
        setStreamingStage('')
        setStatus('idle')
        setLastUserPrompt(lastPromptRef.current)
        contentRef.current = ''
        sourcesRef.current = []
        stageRef.current = ''
        streamStartRef.current = 0
        partialDebugRef.current = null
      }
    } finally {
      abortRef.current = null
    }
  }, [])

  const retryLast = useCallback((sessionId: number) => {
    const prompt = lastPromptRef.current
    if (!prompt) return
    setMessages(prev => {
      const last = prev[prev.length - 1]
      if (last?.error_code) return prev.slice(0, -1)
      return prev
    })
    sendMessage(sessionId, prompt)
  }, [sendMessage])

  return { messages, setMessages, streamingContent, streamingSources, streamingStage, status, lastUserPrompt, sendMessage, cancel, reset, retryLast }
}
