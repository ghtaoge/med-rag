import { defineStore } from 'pinia'
import { chatStream, listSessions, deleteSession } from '../services/api'

export const useChatStore = defineStore('chat', {
  state: () => ({
    question: '',
    answer: '',
    isStreaming: false,
    isLlmFallback: false,
    sources: [],
    intent: null,
    correctness: null,
    sessions: [],
    eventSource: null,
    safetyAssessment: null,
    safetyError: null,
  }),

  actions: {
    // SSE 流式问答
    startStream(question) {
      this.question = question
      this.answer = ''
      this.isLlmFallback = false
      this.sources = []
      this.intent = null
      this.correctness = null
      this.safetyAssessment = null
      this.safetyError = null
      this.isStreaming = true

      this.eventSource = chatStream(question, {
        onSafetyAssessment: (data) => {
          this.safetyAssessment = data
        },
        onSafetyBlocked: (data) => {
          this.handleSafetyBlocked(data)
        },
        onIntent: (data) => {
          this.intent = data
        },
        onSearchStart: (data) => {
          // 检索开始
        },
        onSearchResult: (data) => {
          // 检索完成
        },
        onLlmFallback: (data) => {
          this.isLlmFallback = true
        },
        onGenerationStart: (data) => {
          // LLM 生成开始
        },
        onToken: (data) => {
          this.answer += data.content
        },
        onGenerationEnd: (data) => {
          this.sources = (data.sources || []).map(source => ({
            ...source,
            content_preview: source.content_preview || source.content || '',
          }))
        },
        onCorrectness: (data) => {
          this.correctness = data
        },
        onDone: (data) => {
          this.isStreaming = false
        },
        onError: (data) => {
          this.isStreaming = false
          if (data.code === 'SAFETY_POLICY_BLOCKED' || data.code === 'OUTPUT_SAFETY_BLOCKED') {
            this.handleSafetyBlocked(data)
          } else {
            this.answer += `\n\n错误: ${data.message || '未知错误'}`
          }
        },
      })
    },

    handleSafetyBlocked(data) {
      this.answer = ''
      this.sources = []
      this.correctness = null
      this.isStreaming = false
      this.safetyError = data
      this.eventSource?.close()
      this.eventSource = null
    },

    // 停止流式
    stopStream() {
      if (this.eventSource) {
        this.eventSource.close()
        this.eventSource = null
      }
      this.isStreaming = false
    },

    // 加载历史会话
    async loadSessions() {
      try {
        const res = await listSessions()
        this.sessions = res.data.sessions || []
      } catch (e) {
        this.sessions = []
      }
    },

    // 删除会话
    async removeSession(sessionId) {
      await deleteSession(sessionId)
      this.sessions = this.sessions.filter(s => s.session_id !== sessionId)
    },

    // 清空当前问答
    clearChat() {
      this.question = ''
      this.answer = ''
      this.isLlmFallback = false
      this.sources = []
      this.intent = null
      this.correctness = null
      this.safetyAssessment = null
      this.safetyError = null
    },
  },
})
