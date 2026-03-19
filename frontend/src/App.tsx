import { useCallback, useEffect, useState } from 'react'
import { createSession, deleteSession, getSession, listSessions } from './api/chat'
import { ChatWindow } from './components/ChatWindow'
import { FileUpload } from './components/FileUpload'
import { Layout } from './components/Layout'
import { useChat } from './hooks/useChat'
import { useTheme } from './hooks/useTheme'
import type { ChatSession } from './types'

export default function App() {
  const { theme, toggle: toggleTheme } = useTheme()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)
  const { messages, setMessages, streamingContent, streamingSources, status, lastUserPrompt, sendMessage, cancel, reset } = useChat()

  const [showUpload, setShowUpload] = useState(false)

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
    reset()
    try {
      const session = await createSession()
      setSessions(prev => [session, ...prev])
      setActiveSessionId(session.id)
    } catch {
      // ignore
    }
  }, [reset])

  const handleSelectSession = useCallback(async (id: number) => {
    reset()
    setActiveSessionId(id)
    try {
      const detail = await getSession(id)
      setMessages(detail.messages)
    } catch {
      // messages already cleared by reset()
    }
  }, [reset, setMessages])

  const handleDeleteSession = useCallback(async (id: number) => {
    try {
      await deleteSession(id)
      setSessions(prev => prev.filter(s => s.id !== id))
      if (activeSessionId === id) {
        reset()
        setActiveSessionId(null)
      }
    } catch {
      // ignore
    }
  }, [activeSessionId, reset])

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
        onSend={handleSend}
        onCancel={cancel}
        editValue={lastUserPrompt}
        onUploadClick={() => setShowUpload(true)}
      />
      {showUpload && (
        <FileUpload
          onClose={() => setShowUpload(false)}
          onComplete={() => setShowUpload(false)}
        />
      )}
    </Layout>
  )
}
