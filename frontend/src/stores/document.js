import { defineStore } from 'pinia'
import { listDocuments, uploadDocument, syncAllDocuments, deleteDocument } from '../services/api'

export const useDocumentStore = defineStore('document', {
  state: () => ({
    documents: [],
    totalFiles: 0,
    totalChunks: 0,
    uploading: false,
    syncing: false,
  }),

  actions: {
    async loadDocuments() {
      try {
        const res = await listDocuments()
        this.documents = res.data.documents || []
        this.totalFiles = res.data.total_files || 0
        this.totalChunks = res.data.total_chunks || 0
      } catch (e) {
        this.documents = []
      }
    },

    async upload(file) {
      this.uploading = true
      try {
        const res = await uploadDocument(file)
        await this.loadDocuments()
        return res.data
      } finally {
        this.uploading = false
      }
    },

    async syncAll() {
      this.syncing = true
      try {
        const res = await syncAllDocuments()
        await this.loadDocuments()
        return res.data
      } finally {
        this.syncing = false
      }
    },

    async remove(filename) {
      await deleteDocument(filename)
      await this.loadDocuments()
    },
  },
})
