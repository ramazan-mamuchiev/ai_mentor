import { useCallback, useEffect, useRef, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { createSession, deleteSession, getSession, listSessions, updateSession } from '../api/chat'
import { ChatWindow } from '../components/ChatWindow'
import { FileUpload, type ProductContext } from '../components/FileUpload'
import { UrlImport } from '../components/UrlImport'
import { Layout } from '../components/Layout'
import { ProductPicker } from '../components/ProductPicker'
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
  const [showProductPicker, setShowProductPicker] = useState(false)

  const handleProductDetected = useCallback((sessionId: number, update: {
    product_filter?: string | null
    product_filter_source?: string | null
    version_filter?: string | null
    auto_product?: string | null
  }) => {
    setSessions(prev => prev.map(s =>
      s.id === sessionId ? {
        ...s,
        product_filter: update.product_filter ?? s.product_filter,
        product_filter_source: update.product_filter_source ?? s.product_filter_source,
      } : s,
    ))
  }, [])

  const { messages, setMessages, streamingContent, streamingSources, status, lastUserPrompt, sendMessage, cancel, reset, retryLast } = useChat({
    onProductDetected: handleProductDetected,
  })

  const [showUpload, setShowUpload] = useState(false)
  const [showUrlImport, setShowUrlImport] = useState(false)
  const [docsRefreshKey, setDocsRefreshKey] = useState(0)
  const productContextRef = useRef<ProductContext | undefined>(undefined)

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

  const handleProductChange = useCallback(async (selection: {
    productName: string | null
    manufacturer: string | null
    versionFilter: string | null
  }) => {
    if (!activeSessionId) return

    try {
      const updated = await updateSession(activeSessionId, {
        product_filter: selection.productName,
        version_filter: selection.versionFilter,
      })
      setSessions(prev => prev.map(s =>
        s.id === activeSessionId ? {
          ...s,
          product_filter: updated.product_filter,
          product_filter_source: updated.product_filter_source,
          version_filter: updated.version_filter,
        } : s,
      ))
    } catch {
      // ignore
    }
  }, [activeSessionId])

  const handleClearProduct = useCallback(async () => {
    if (!activeSessionId) return
    try {
      const updated = await updateSession(activeSessionId, {
        product_filter: '',
        version_filter: '',
      })
      setSessions(prev => prev.map(s =>
        s.id === activeSessionId ? {
          ...s,
          product_filter: updated.product_filter,
          product_filter_source: updated.product_filter_source,
          version_filter: updated.version_filter,
        } : s,
      ))
    } catch {
      // ignore
    }
  }, [activeSessionId])

  const handleLockProduct = useCallback(async () => {
    if (!activeSessionId) return
    try {
      const updated = await updateSession(activeSessionId, {
        product_filter_source: 'explicit',
      })
      setSessions(prev => prev.map(s =>
        s.id === activeSessionId ? {
          ...s,
          product_filter_source: updated.product_filter_source,
        } : s,
      ))
    } catch {
      // ignore
    }
  }, [activeSessionId])

  const handleUnlockProduct = useCallback(async () => {
    if (!activeSessionId) return
    try {
      const updated = await updateSession(activeSessionId, {
        product_filter_source: 'auto',
      })
      setSessions(prev => prev.map(s =>
        s.id === activeSessionId ? {
          ...s,
          product_filter_source: updated.product_filter_source,
        } : s,
      ))
    } catch {
      // ignore
    }
  }, [activeSessionId])

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
      productFilter={activeSession?.product_filter}
      versionFilter={activeSession?.version_filter}
      autoDetected={activeSession?.product_filter_source === 'auto'}
      productLocked={activeSession?.product_filter_source === 'explicit'}
      onEditProduct={() => setShowProductPicker(true)}
      onClearProduct={handleClearProduct}
      onLockProduct={handleLockProduct}
      onUnlockProduct={handleUnlockProduct}
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
        <Route path="documents" element={<DocumentsPage onUploadClick={() => { productContextRef.current = undefined; setShowUpload(true) }} onUrlImportClick={() => { productContextRef.current = undefined; setShowUrlImport(true) }} refreshKey={docsRefreshKey} />} />
        <Route path="products" element={<ProductsPage onUploadClick={() => { productContextRef.current = undefined; setShowUpload(true) }} onUrlImportClick={() => { productContextRef.current = undefined; setShowUrlImport(true) }} refreshKey={docsRefreshKey} />} />
        <Route path="products/:manufacturer/:product" element={
          <ProductDetailPage
            onUploadClick={(ctx) => { productContextRef.current = ctx; setShowUpload(true) }}
            onUrlImportClick={(ctx) => { productContextRef.current = ctx; setShowUrlImport(true) }}
          />
        } />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
      {showUpload && (
        <FileUpload
          onClose={() => setShowUpload(false)}
          onComplete={() => {
            setDocsRefreshKey(k => k + 1)
          }}
          productContext={productContextRef.current}
        />
      )}
      {showUrlImport && (
        <UrlImport
          onClose={() => setShowUrlImport(false)}
          onComplete={() => {
            setDocsRefreshKey(k => k + 1)
          }}
          productContext={productContextRef.current}
        />
      )}
      {showProductPicker && (
        <ProductPicker
          value={{
            productName: activeSession?.product_filter ?? null,
            manufacturer: null,
            versionFilter: activeSession?.version_filter ?? null,
          }}
          onChange={handleProductChange}
          onClose={() => setShowProductPicker(false)}
        />
      )}
    </Layout>
  )
}
