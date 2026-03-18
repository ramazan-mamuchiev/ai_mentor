import http from 'node:http'

const PORT = 3999
let nextSessionId = 1
let sessions: Record<number, any> = {}
let messages: Record<number, any[]> = {}

function now() {
  return new Date().toISOString()
}

function resetState() {
  nextSessionId = 1
  sessions = {}
  messages = {}
}

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let data = ''
    req.on('data', (chunk: Buffer) => { data += chunk.toString() })
    req.on('end', () => resolve(data))
  })
}

function json(res: http.ServerResponse, status: number, body: any) {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(body))
}

const server = http.createServer(async (req, res) => {
  const url = req.url || ''
  const method = req.method || 'GET'

  if (method === 'POST' && url === '/api/v1/e2e/reset') {
    resetState()
    json(res, 200, { ok: true })
    return
  }

  if (url === '/health' && method === 'GET') {
    json(res, 200, { status: 'ok' })
    return
  }

  if (method === 'POST' && url === '/api/v1/chat/sessions') {
    const raw = await readBody(req)
    const body = raw ? JSON.parse(raw) : {}
    const id = nextSessionId++
    const session = {
      id,
      title: body.title || null,
      device_filter: body.device_filter || null,
      version_filter: body.version_filter || null,
      created_at: now(),
      updated_at: now(),
      message_count: 0,
    }
    sessions[id] = session
    messages[id] = []
    json(res, 201, session)
    return
  }

  if (method === 'GET' && url === '/api/v1/chat/sessions') {
    const list = Object.values(sessions)
      .sort((a: any, b: any) => b.id - a.id)
      .map((s: any) => ({
        ...s,
        message_count: (messages[s.id] || []).length,
        last_message_preview: (messages[s.id] || [])
          .filter((m: any) => m.role === 'user')
          .pop()?.content?.slice(0, 100) || null,
      }))
    json(res, 200, list)
    return
  }

  const sessionMatch = url.match(/^\/api\/v1\/chat\/sessions\/(\d+)$/)
  if (sessionMatch) {
    const id = Number(sessionMatch[1])
    if (method === 'GET') {
      const session = sessions[id]
      if (!session) { json(res, 404, { detail: 'Session not found' }); return }
      json(res, 200, { ...session, messages: messages[id] || [] })
      return
    }
    if (method === 'DELETE') {
      if (!sessions[id]) { json(res, 404, { detail: 'Session not found' }); return }
      delete sessions[id]
      delete messages[id]
      res.writeHead(204)
      res.end()
      return
    }
  }

  const msgMatch = url.match(/^\/api\/v1\/chat\/sessions\/(\d+)\/messages$/)
  if (msgMatch && method === 'POST') {
    const id = Number(msgMatch[1])
    const session = sessions[id]
    if (!session) { json(res, 404, { detail: 'Session not found' }); return }

    const raw = await readBody(req)
    const body = raw ? JSON.parse(raw) : {}
    const userContent = body.content || ''

    const userMsg = {
      id: Date.now(),
      session_id: id,
      role: 'user',
      content: userContent,
      sources: null,
      duration_ms: null,
      created_at: now(),
    }
    if (!messages[id]) messages[id] = []
    messages[id].push(userMsg)

    if (!session.title && userContent) {
      session.title = userContent.slice(0, 80)
    }
    session.updated_at = now()

    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    })

    const sources = [
      {
        doc_title: 'HikCentral API Guide',
        heading_path: 'Authentication > HMAC-SHA256',
        similarity: 0.92,
        content_preview: 'Use HMAC-SHA256 to sign requests...',
        device_name: 'HikCentral',
        firmware_version: '2.6',
      },
    ]

    const tokens = ['This ', 'is ', 'a ', 'mock ', 'response ', 'from ', 'the ', 'AI ', 'assistant.']
    const msgId = Date.now() + 1

    res.write(`data: ${JSON.stringify({ type: 'sources', sources })}\n\n`)

    let i = 0
    const interval = setInterval(() => {
      if (i < tokens.length) {
        res.write(`data: ${JSON.stringify({ type: 'token', content: tokens[i] })}\n\n`)
        i++
      } else {
        clearInterval(interval)
        const fullContent = tokens.join('')
        const durationMs = tokens.length * 50

        const assistantMsg = {
          id: msgId,
          session_id: id,
          role: 'assistant',
          content: fullContent,
          sources,
          duration_ms: durationMs,
          created_at: now(),
        }
        if (messages[id]) messages[id].push(assistantMsg)

        res.write(`data: ${JSON.stringify({ type: 'done', message_id: msgId, duration_ms: durationMs })}\n\n`)
        res.end()
      }
    }, 50)

    req.on('close', () => {
      clearInterval(interval)
    })
    return
  }

  json(res, 404, { detail: 'Not found' })
})

server.listen(PORT, () => {
  console.log(`Mock API server running on http://localhost:${PORT}`)
})
