import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useChatStore } from './chat'

describe('chat safety state', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('clears generated content after an output block', () => {
    const store = useChatStore()
    store.answer = 'partial unsafe content'
    store.sources = [{ id: 'source' }]
    store.handleSafetyBlocked({
      code: 'OUTPUT_SAFETY_BLOCKED',
      message: '输出未通过安全检查',
    })
    expect(store.answer).toBe('')
    expect(store.sources).toEqual([])
    expect(store.safetyError.code).toBe('OUTPUT_SAFETY_BLOCKED')
  })
})
