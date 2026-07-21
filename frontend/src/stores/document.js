import { defineStore } from 'pinia'

import {
  approveDocument,
  getParseJob,
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
    jobs: {},
    polling: {},
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
        for (const document of this.documents) {
          if (document.parse_job_id) {
            this.applyJob({
              id: document.parse_job_id,
              document_id: document.document_id,
              status: document.processing_status,
              error_code: document.processing_error_code,
            })
            if (!this.jobs[document.parse_job_id].terminal) {
              this.pollJob(document.parse_job_id)
            }
          }
        }
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
        const result = response.data
        if (result.parse_job_id) {
          this.applyJob({
            id: result.parse_job_id,
            document_id: result.document_id,
            status: result.processing_status,
          })
          this.pollJob(result.parse_job_id)
        }
        return result
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

    applyJob(job) {
      const terminal = ['ready_for_review', 'infected', 'failed'].includes(job.status)
      this.jobs[job.id] = {
        ...this.jobs[job.id],
        ...job,
        terminal,
        canRetry: job.status === 'failed',
      }
      const document = this.documents.find(item => item.parse_job_id === job.id)
      if (document) {
        document.processing_status = job.status
        document.processing_error_code = job.error_code || null
      }
    },

    async pollJob(jobId) {
      if (this.polling[jobId]) return
      this.polling[jobId] = true
      const intervals = [1000, 2000, 4000, 8000]
      let attempt = 0
      try {
        while (this.polling[jobId]) {
          const response = await getParseJob(jobId)
          this.applyJob(response.data)
          if (this.jobs[jobId].terminal) {
            await this.loadDocuments()
            break
          }
          const delay = intervals[Math.min(attempt, intervals.length - 1)]
          attempt += 1
          await new Promise(resolve => window.setTimeout(resolve, delay))
        }
      } finally {
        delete this.polling[jobId]
      }
    },

    stopPolling() {
      for (const jobId of Object.keys(this.polling)) delete this.polling[jobId]
    },
  },
})
