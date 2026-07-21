import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useDocumentStore } from './document'

describe('document processing jobs', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('marks infected jobs as non-retryable', () => {
    const store = useDocumentStore()
    store.applyJob({
      id: 'job-1',
      status: 'infected',
      error_code: 'MALWARE_DETECTED',
    })
    expect(store.jobs['job-1'].canRetry).toBe(false)
    expect(store.jobs['job-1'].terminal).toBe(true)
  })
})
