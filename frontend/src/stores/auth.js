import { defineStore } from 'pinia'
import {
  configureAuth,
  getCurrentUser,
  loginRequest,
  logoutRequest,
  refreshSession,
  setAccessToken,
} from '../services/api'

const ROLE_PERMISSIONS = {
  reader: ['chat', 'document_read'],
  knowledge_editor: ['chat', 'document_read', 'document_edit'],
  knowledge_reviewer: ['chat', 'document_read', 'document_approve'],
  department_admin: ['chat', 'document_read', 'department_admin'],
  security_auditor: ['security_audit'],
  platform_admin: ['platform_config'],
}

const sessionStore = typeof sessionStorage === 'undefined'
  ? { getItem: () => '', setItem: () => {}, removeItem: () => {} }
  : sessionStorage

export const useAuthStore = defineStore('auth', {
  state: () => ({
    accessToken: '',
    csrfToken: sessionStore.getItem('med-rag-csrf') || '',
    user: null,
    initialized: false,
  }),

  getters: {
    isAuthenticated: state => Boolean(state.accessToken && state.user),
    permissions: state => {
      if (Array.isArray(state.user?.permissions)) {
        return new Set(state.user.permissions)
      }
      const values = new Set()
      for (const membership of state.user?.memberships || []) {
        for (const permission of ROLE_PERMISSIONS[membership.role] || []) {
          values.add(permission)
        }
      }
      return values
    },
    hasPermission() {
      return permission => this.permissions.has(permission)
    },
    editableDepartments: state => (state.user?.memberships || [])
      .filter(item => ['knowledge_editor'].includes(item.role))
      .map(item => item.department_id),
  },

  actions: {
    _applyTokens(tokens) {
      this.accessToken = tokens.access_token || ''
      this.csrfToken = tokens.csrf_token || ''
      setAccessToken(this.accessToken)
      if (this.csrfToken) sessionStore.setItem('med-rag-csrf', this.csrfToken)
    },

    clear() {
      this.accessToken = ''
      this.csrfToken = ''
      this.user = null
      setAccessToken('')
      sessionStore.removeItem('med-rag-csrf')
    },

    async loadUser() {
      const response = await getCurrentUser()
      this.user = response.data
      return this.user
    },

    async login(username, password) {
      const response = await loginRequest(username, password)
      this._applyTokens(response.data)
      await this.loadUser()
    },

    async initialize() {
      if (this.initialized) return
      configureAuth({
        onTokens: tokens => this._applyTokens(tokens),
        onLogout: () => this.clear(),
      })
      try {
        if (this.csrfToken) {
          const tokens = await refreshSession()
          this._applyTokens(tokens)
          await this.loadUser()
        }
      } catch {
        this.clear()
      } finally {
        this.initialized = true
      }
    },

    async logout() {
      try {
        await logoutRequest()
      } finally {
        this.clear()
      }
    },
  },
})
