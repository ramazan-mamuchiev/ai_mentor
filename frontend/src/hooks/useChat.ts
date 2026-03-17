import { useCallback, useRef, useState } from 'react'
import { streamMessage } from '../api/chat'
import type { ChatMessage, SourceInfo, StreamStatus } from '../types'

interface UseChatReturn {
  messages: ChatMessage[]
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  streamingContent: string
  streamingSources: SourceInfo[]
  status: StreamStatus
  sendMessage: (sessionId: number, content: string) => Promise<void>
  cancel: () => void
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingSources, setStreamingSources] = useState<SourceInfo[]>([])
  const [status, setStatus] = useState<StreamStatus>('idle')
  const abortRef = useRef<AbortController | null>(null)

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStatus('idle')
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

    const controller = new AbortController()
    abortRef.current = controller

    try {
      let fullContent = ''
      let sources: SourceInfo[] = []
      let msgId = 0
      let durationMs = 0

      for await (const event of streamMessage(sessionId, content, controller.signal)) {
        switch (event.type) {
          case 'token':
            fullContent += event.content
            setStreamingContent(fullContent)
            break
          case 'sources':
            sources = event.sources
            setStreamingSources(sources)
            break
          case 'done':
            msgId = event.message_id
            durationMs = event.duration_ms
            break
          case 'error':
            setStatus('error')
            fullContent += `\n\n⚠️ Error: ${event.content}`
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
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, assistantMsg])
      setStreamingContent('')
      setStreamingSources([])
      setStatus('idle')
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setStatus('error')
      }
    } finally {
      abortRef.current = null
    }
  }, [])

  return { messages, setMessages, streamingContent, streamingSources, status, sendMessage, cancel }
}
