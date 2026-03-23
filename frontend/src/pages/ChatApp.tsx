import { useCallback, useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { createSession, deleteSession, getSession, listSessions } from '../api/chat'
import { ChatWindow } from '../components/ChatWindow'
import { FileUpload } from '../components/FileUpload'
import { Layout } from '../components/Layout'
import { useChat } from '../hooks/useChat'
import { useTheme } from '../hooks/useTheme'
import type { ChatSession } from '../types'
import { DocumentsPage } from './DocumentsPage'
import { ProductsPage } from './ProductsPage'
import { ProductDetailPage } from './ProductDetailPage'
import { AnalyticsPage } from './AnalyticsPage'
import { SettingsPage } from './SettingsPage'

export function ChatApp() {
  const { theme, toggle: toggleTheme } = useTheme()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)
  const { messages, setMessages, streamingContent, streamingSources, status, lastUserPrompt, sendMessage, cancel, reset, retryLast } = useChat()

  const [showUpload, setShowUpload] = useState(false)
  const [docsRefreshKey, setDocsRefreshKey] = useState(0)

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
        setMessages([
          { id: Date.now(), session_id: 0, role: 'user', content, created_at: new Date().toISOString() },
          { id: Date.now() + 1, session_id: 0, role: 'assistant', content: '', error_code: 'networkError', created_at: new Date().toISOString() },
        ])
        return
      }
    }
    await sendMessage(sessionId, content)
    refreshSessions()
  }, [activeSessionId, sendMessage, setMessages, refreshSessions])

  const chatContent = (
    <ChatWindow
      messages={messages}
      streamingContent={streamingContent}
      streamingSources={streamingSources}
      status={status}
      onSend={handleSend}
      onCancel={cancel}
      onRetry={activeSessionId
        ? () => retryLast(activeSessionId)
        : messages.length > 0
          ? () => {
              const userMsg = [...messages].reverse().find(m => m.role === 'user')
              if (userMsg) { setMessages([]); handleSend(userMsg.content) }
            }
          : undefined
      }
      editValue={lastUserPrompt}
      onUploadClick={() => setShowUpload(true)}
    />
  )

  return (
    <Layout
      sessions={sessions}
      activeSessionId={activeSessionId}
      theme={theme}
      onSelectSession={handleSelectSession}
      onNewSession={handleNewSession}
      onDeleteSession={handleDeleteSession}
      onToggleTheme={toggleTheme}
      onLogoClick={() => { reset(); setActiveSessionId(null) }}
    >
      <Routes>
        <Route index element={chatContent} />
        <Route path="documents" element={<DocumentsPage onUploadClick={() => setShowUpload(true)} refreshKey={docsRefreshKey} />} />
        <Route path="products" element={<ProductsPage onUploadClick={() => setShowUpload(true)} />} />
        <Route path="products/:id" element={<ProductDetailPage onUploadClick={() => setShowUpload(true)} />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
      {showUpload && (
        <FileUpload
          onClose={() => setShowUpload(false)}
          onComplete={() => {
            setShowUpload(false)
            setDocsRefreshKey(k => k + 1)
          }}
        />
      )}
    </Layout>
  )
}
