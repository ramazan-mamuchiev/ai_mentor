import { useCallback, useRef, useState } from 'react'
import { streamMessage } from '../api/chat'
import type { ChatMessage, DebugInfo, SourceInfo, StreamStatus } from '../types'

interface UseChatReturn {
  messages: ChatMessage[]
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  streamingContent: string
  streamingSources: SourceInfo[]
  status: StreamStatus
  lastUserPrompt: string
  sendMessage: (sessionId: number, content: string) => Promise<void>
  cancel: () => void
  reset: () => void
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingSources, setStreamingSources] = useState<SourceInfo[]>([])
  const [status, setStatus] = useState<StreamStatus>('idle')
  const [lastUserPrompt, setLastUserPrompt] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const contentRef = useRef('')
  const sourcesRef = useRef<SourceInfo[]>([])
  const lastPromptRef = useRef('')

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null

    const partial = contentRef.current
    const partialSources = sourcesRef.current
    if (partial) {
      const stoppedMsg: ChatMessage = {
        id: Date.now() + 1,
        session_id: 0,
        role: 'assistant',
        content: partial + '\n\n*⏹ Generation stopped*',
        sources: partialSources.length > 0 ? partialSources : undefined,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, stoppedMsg])
    }

    setStreamingContent('')
    setStreamingSources([])
    setStatus('idle')
    setLastUserPrompt(lastPromptRef.current)
    contentRef.current = ''
    sourcesRef.current = []
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setStreamingContent('')
    setStreamingSources([])
    setStatus('idle')
    setLastUserPrompt('')
    contentRef.current = ''
    sourcesRef.current = []
    lastPromptRef.current = ''
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
    setStatus('streaming')
    setLastUserPrompt('')
    contentRef.current = ''
    sourcesRef.current = []
    lastPromptRef.current = content

    const controller = new AbortController()
    abortRef.current = controller

    try {
      let fullContent = ''
      let sources: SourceInfo[] = []
      let msgId = 0
      let durationMs = 0
      let debugInfo: DebugInfo | null = null

      for await (const event of streamMessage(sessionId, content, controller.signal)) {
        switch (event.type) {
          case 'token':
            fullContent += event.content
            contentRef.current = fullContent
            setStreamingContent(fullContent)
            break
          case 'sources':
            sources = event.sources
            sourcesRef.current = sources
            setStreamingSources(sources)
            break
          case 'done':
            msgId = event.message_id
            durationMs = event.duration_ms
            debugInfo = event.debug ?? null
            break
          case 'error':
            setStatus('error')
            fullContent += `\n\n⚠️ Error: ${event.content}`
            contentRef.current = fullContent
            setStreamingContent(fullContent)
            return
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
      setStatus('idle')
      contentRef.current = ''
      sourcesRef.current = []
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setStatus('error')
      }
    } finally {
      abortRef.current = null
    }
  }, [])

  return { messages, setMessages, streamingContent, streamingSources, status, lastUserPrompt, sendMessage, cancel, reset }
}
