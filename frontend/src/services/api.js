import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
})

// 问答 — 非流式
export function chatComplete(question) {
  return api.post('/api/v1/chat/complete', null, { params: { question } })
}

// 问答 — SSE 流式
export function chatStream(question, callbacks) {
  const url = `/api/v1/chat/stream?question=${encodeURIComponent(question)}`

  const eventSource = new EventSource(url)

  eventSource.addEventListener('intent', (e) => {
    callbacks.onIntent?.(JSON.parse(e.data))
  })

  eventSource.addEventListener('search_start', (e) => {
    callbacks.onSearchStart?.(JSON.parse(e.data))
  })

  eventSource.addEventListener('search_result', (e) => {
    callbacks.onSearchResult?.(JSON.parse(e.data))
  })

  eventSource.addEventListener('generation_start', (e) => {
    callbacks.onGenerationStart?.(JSON.parse(e.data))
  })

  eventSource.addEventListener('token', (e) => {
    callbacks.onToken?.(JSON.parse(e.data))
  })

  eventSource.addEventListener('generation_end', (e) => {
    callbacks.onGenerationEnd?.(JSON.parse(e.data))
  })

  eventSource.addEventListener('correctness', (e) => {
    callbacks.onCorrectness?.(JSON.parse(e.data))
  })

  eventSource.addEventListener('done', (e) => {
    callbacks.onDone?.(JSON.parse(e.data))
    eventSource.close()
  })

  eventSource.addEventListener('error', (e) => {
    callbacks.onError?.(JSON.parse(e.data))
    eventSource.close()
  })

  eventSource.onerror = () => {
    callbacks.onError?.({ code: 'CONNECTION_ERROR', message: '连接断开' })
    eventSource.close()
  }

  return eventSource
}

// 会话管理
export function listSessions(limit = 20) {
  return api.get('/api/v1/chat/sessions', { params: { limit } })
}

export function getSession(sessionId) {
  return api.get(`/api/v1/chat/sessions/${sessionId}`)
}

export function deleteSession(sessionId) {
  return api.delete(`/api/v1/chat/sessions/${sessionId}`)
}

// 文档管理
export function listDocuments() {
  return api.get('/api/v1/documents/list')
}

export function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/v1/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function syncAllDocuments() {
  return api.post('/api/v1/documents/sync')
}

export function syncSingleDocument(filename) {
  return api.post(`/api/v1/documents/sync/${encodeURIComponent(filename)}`)
}

export function validateDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/v1/documents/validate', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function deleteDocument(filename) {
  return api.delete(`/api/v1/documents/${encodeURIComponent(filename)}`)
}

// 评估
export function getChecklist() {
  return api.get('/api/v1/evaluation/checklist')
}

export function getStats() {
  return api.get('/api/v1/evaluation/stats')
}

// 健康检查
export function healthCheck() {
  return api.get('/health')
}

// 引擎信息
export function getEngines() {
  return api.get('/api/v1/engines')
}
