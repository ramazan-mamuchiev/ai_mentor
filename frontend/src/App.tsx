import { useCallback, useEffect, useState } from 'react'
import { createSession, deleteSession, getSession, listSessions } from './api/chat'
import { ChatWindow } from './components/ChatWindow'
import { Layout } from './components/Layout'
import { useChat } from './hooks/useChat'
import { useTheme } from './hooks/useTheme'
import type { ChatSession } from './types'

export default function App() {
  const { theme, toggle: toggleTheme } = useTheme()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)
  const { messages, setMessages, streamingContent, streamingSources, status, sendMessage, cancel } = useChat()

  const activeSession = sessions.find(s => s.id === activeSessionId) ?? null

  const refreshSessions = useCallback(async () => {
    try {
      const list = await listSessions()
      setSessions(list)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    refreshSessions()
  }, [refreshSessions])

  const handleNewSession = useCallback(async () => {
    try {
      const session = await createSession()
      setSessions(prev => [session, ...prev])
      setActiveSessionId(session.id)
      setMessages([])
    } catch {
      // ignore
    }
  }, [setMessages])

  const handleSelectSession = useCallback(async (id: number) => {
    setActiveSessionId(id)
    try {
      const detail = await getSession(id)
      setMessages(detail.messages)
    } catch {
      setMessages([])
    }
  }, [setMessages])

  const handleDeleteSession = useCallback(async (id: number) => {
    try {
      await deleteSession(id)
      setSessions(prev => prev.filter(s => s.id !== id))
      if (activeSessionId === id) {
        setActiveSessionId(null)
        setMessages([])
      }
    } catch {
      // ignore
    }
  }, [activeSessionId, setMessages])

  const handleSend = useCallback(async (content: string) => {
    let sessionId = activeSessionId
    if (!sessionId) {
      try {
        const session = await createSession()
        setSessions(prev => [session, ...prev])
        setActiveSessionId(session.id)
        sessionId = session.id
      } catch {
        return
      }
    }
    await sendMessage(sessionId, content)
    refreshSessions()
  }, [activeSessionId, sendMessage, refreshSessions])

  return (
    <Layout
      sessions={sessions}
      activeSessionId={activeSessionId}
      theme={theme}
      onSelectSession={handleSelectSession}
      onNewSession={handleNewSession}
      onDeleteSession={handleDeleteSession}
      onToggleTheme={toggleTheme}
    >
      <ChatWindow
        messages={messages}
        streamingContent={streamingContent}
        streamingSources={streamingSources}
        status={status}
        sessionTitle={activeSession?.title ?? null}
        onSend={handleSend}
        onCancel={cancel}
      />
    </Layout>
  )
}
