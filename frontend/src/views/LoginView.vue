<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <div class="login-brand">
        <span class="login-mark"><ShieldCheck :size="24" /></span>
        <div>
          <strong>Med-Rag</strong>
          <span>医疗知识库</span>
        </div>
      </div>

      <header>
        <h1 id="login-title">登录</h1>
        <p>使用公司分配的账号访问授权知识。</p>
      </header>

      <form @submit.prevent="submit">
        <label>
          <span>用户名</span>
          <input
            v-model.trim="username"
            name="username"
            autocomplete="username"
            required
            autofocus
          />
        </label>
        <label>
          <span>密码</span>
          <input
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
          />
        </label>
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <button class="login-submit" type="submit" :disabled="submitting">
          <LoaderCircle v-if="submitting" class="spin" :size="18" />
          <LogIn v-else :size="18" />
          {{ submitting ? '正在验证' : '登录' }}
        </button>
      </form>
    </section>
  </main>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { LoaderCircle, LogIn, ShieldCheck } from 'lucide-vue-next'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const submitting = ref(false)
const error = ref('')

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (requestError) {
    error.value = requestError.response?.data?.message || '用户名或密码错误'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--bg-primary);
}

.login-panel {
  width: min(100%, 400px);
  padding: 28px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color);
}

.login-mark {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 8px;
  background: var(--accent-color);
  color: white;
}

.login-brand strong,
.login-brand span {
  display: block;
}

.login-brand strong {
  font-size: 17px;
}

.login-brand div > span,
header p {
  color: var(--text-secondary);
  font-size: 13px;
}

header {
  margin: 24px 0 20px;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

header p {
  margin: 6px 0 0;
}

form,
label {
  display: grid;
  gap: 8px;
}

form {
  gap: 16px;
}

label span {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
}

input {
  width: 100%;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  outline: none;
  background: var(--bg-primary);
  color: var(--text-primary);
}

input:focus {
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px var(--accent-color-light);
}

.login-submit {
  min-height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-radius: 8px;
  background: var(--accent-color);
  color: white;
  font-weight: 600;
}

.login-submit:disabled {
  opacity: 0.6;
}

.login-error {
  margin: 0;
  color: var(--red);
  font-size: 13px;
}

.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
