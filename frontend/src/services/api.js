import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
  withCredentials: true,
})

let accessToken = ''
let refreshPromise = null
let authCallbacks = { onTokens: null, onLogout: null }

export function configureAuth(callbacks) {
  authCallbacks = { ...authCallbacks, ...callbacks }
}

export function setAccessToken(token) {
  accessToken = token || ''
}

function applyTokens(data) {
  setAccessToken(data.access_token)
  if (data.csrf_token) sessionStorage.setItem('med-rag-csrf', data.csrf_token)
  authCallbacks.onTokens?.(data)
  return data
}

async function refreshAccessToken() {
  const csrfToken = sessionStorage.getItem('med-rag-csrf')
  if (!csrfToken) throw new Error('No refresh session')
  const response = await axios.post(
    '/api/v1/auth/refresh',
    null,
    {
      withCredentials: true,
      headers: { 'X-CSRF-Token': csrfToken },
    },
  )
  return applyTokens(response.data)
}

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

api.interceptors.response.use(
  response => response,
  async (error) => {
    const request = error.config
    const isAuthRoute = request?.url?.startsWith('/api/v1/auth/')
    if (error.response?.status !== 401 || request?._authRetry || isAuthRoute) {
      throw error
    }
    request._authRetry = true
    try {
      refreshPromise ||= refreshAccessToken().finally(() => { refreshPromise = null })
      await refreshPromise
      return api(request)
    } catch (refreshError) {
      setAccessToken('')
      authCallbacks.onLogout?.()
      throw refreshError
    }
  },
)

export async function loginRequest(username, password) {
  const response = await api.post('/api/v1/auth/login', { username, password })
  applyTokens(response.data)
  return response
}

export async function refreshSession() {
  return refreshAccessToken()
}

export function getCurrentUser() {
  return api.get('/api/v1/auth/me')
}

export async function logoutRequest() {
  const csrfToken = sessionStorage.getItem('med-rag-csrf')
  try {
    await api.post('/api/v1/auth/logout', null, {
      headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
    })
  } finally {
    setAccessToken('')
    sessionStorage.removeItem('med-rag-csrf')
  }
}

export function reauthenticate(password) {
  return api.post('/api/v1/auth/reauthenticate', { password })
}

export function changePassword(currentPassword, newPassword) {
  return api.post('/api/v1/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export function chatComplete(question) {
  return api.post('/api/v1/chat/complete', null, { params: { question } })
}

const SSE_CALLBACKS = {
  intent: 'onIntent',
  search_start: 'onSearchStart',
  search_result: 'onSearchResult',
  llm_fallback: 'onLlmFallback',
  generation_start: 'onGenerationStart',
  token: 'onToken',
  generation_end: 'onGenerationEnd',
  correctness: 'onCorrectness',
  done: 'onDone',
  error: 'onError',
}

export async function consumeSseStream(stream, callbacks) {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() || ''
    for (const frame of frames) {
      let event = 'message'
      const dataLines = []
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (!dataLines.length) continue
      let data
      try {
        data = JSON.parse(dataLines.join('\n'))
      } catch {
        data = { message: '服务返回了无效事件数据' }
        event = 'error'
      }
      callbacks[SSE_CALLBACKS[event]]?.(data)
    }
    if (done) break
  }
}

export function chatStream(question, callbacks) {
  const controller = new AbortController()
  const run = async () => {
    try {
      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        credentials: 'include',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      })
      if (!response.ok || !response.body) {
        throw new Error(`chat stream failed: ${response.status}`)
      }
      await consumeSseStream(response.body, callbacks)
    } catch (error) {
      if (error.name !== 'AbortError') {
        callbacks.onError?.({ code: 'CONNECTION_ERROR', message: '连接已断开' })
      }
    }
  }
  run()
  return { close: () => controller.abort() }
}

export function listSessions(limit = 20) {
  return api.get('/api/v1/chat/sessions', { params: { limit } })
}

export function getSession(sessionId) {
  return api.get(`/api/v1/chat/sessions/${sessionId}`)
}

export function deleteSession(sessionId) {
  return api.delete(`/api/v1/chat/sessions/${sessionId}`)
}

export function listDocuments() {
  return api.get('/api/v1/documents')
}

export function uploadDocument(
  file,
  ownerDepartmentId,
  visibility = 'department_only',
  visibleDepartmentIds = [],
) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('owner_department_id', ownerDepartmentId)
  formData.append('visibility', visibility)
  formData.append('visible_department_ids', JSON.stringify(visibleDepartmentIds))
  return api.post('/api/v1/documents', formData)
}

export function submitDocument(documentId, reason) {
  return api.post(`/api/v1/documents/${documentId}/submit-review`, { reason })
}

export function approveDocument(documentId, reason, reauthenticationToken) {
  return api.post(
    `/api/v1/documents/${documentId}/approve`,
    { reason },
    { headers: { 'X-Reauthentication-Token': reauthenticationToken } },
  )
}

export function revokeDocument(documentId, reason, reauthenticationToken) {
  return api.post(
    `/api/v1/documents/${documentId}/revoke`,
    { reason },
    { headers: { 'X-Reauthentication-Token': reauthenticationToken } },
  )
}

export function syncDocument(documentId) {
  return api.post(`/api/v1/documents/${documentId}/sync`)
}

export function getChecklist() {
  return api.get('/api/v1/evaluation/checklist')
}

export function getStats() {
  return api.get('/api/v1/evaluation/stats')
}

export function healthCheck() {
  return api.get('/health')
}

export function getEngines() {
  return api.get('/api/v1/engines')
}

export default api
