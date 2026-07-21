import { defineStore } from 'pinia'

import {
  approveDocument,
  listDocuments,
  reauthenticate,
  revokeDocument,
  submitDocument,
  syncDocument,
  uploadDocument,
} from '../services/api'

export const useDocumentStore = defineStore('document', {
  state: () => ({
    documents: [],
    uploading: false,
    workingDocumentId: '',
  }),

  getters: {
    totalFiles: state => state.documents.length,
    totalChunks: () => 0,
  },

  actions: {
    async loadDocuments() {
      try {
        const response = await listDocuments()
        this.documents = response.data.documents || []
      } catch {
        this.documents = []
      }
    },

    async upload(file, ownerDepartmentId, visibility, visibleDepartmentIds) {
      this.uploading = true
      try {
        const response = await uploadDocument(
          file,
          ownerDepartmentId,
          visibility,
          visibleDepartmentIds,
        )
        await this.loadDocuments()
        return response.data
      } finally {
        this.uploading = false
      }
    },

    async submit(documentId, reason) {
      return this._run(documentId, async () => {
        await submitDocument(documentId, reason)
      })
    },

    async approve(documentId, reason, password) {
      return this._run(documentId, async () => {
        const auth = await reauthenticate(password)
        await approveDocument(documentId, reason, auth.data.reauthentication_token)
      })
    },

    async revoke(documentId, reason, password) {
      return this._run(documentId, async () => {
        const auth = await reauthenticate(password)
        await revokeDocument(documentId, reason, auth.data.reauthentication_token)
      })
    },

    async sync(documentId) {
      return this._run(documentId, async () => {
        await syncDocument(documentId)
      })
    },

    async _run(documentId, operation) {
      this.workingDocumentId = documentId
      try {
        await operation()
        await this.loadDocuments()
      } finally {
        this.workingDocumentId = ''
      }
    },
  },
})
