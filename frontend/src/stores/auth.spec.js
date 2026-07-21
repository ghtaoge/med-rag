import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from './auth'

describe('auth store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('clears access state on logout', () => {
    const store = useAuthStore()
    store.accessToken = 'token'
    store.user = { username: 'reader' }
    store.clear()
    expect(store.accessToken).toBe('')
    expect(store.user).toBeNull()
  })
})
