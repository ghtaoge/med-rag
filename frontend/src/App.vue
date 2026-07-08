<template>
  <div class="app-frame" :data-theme="theme">
    <aside class="app-sidebar">
      <button class="brand" type="button" @click="go('/chat')" aria-label="Med-Rag 首页">
        <span class="brand-mark" aria-hidden="true">
          <span class="brand-aura"></span>
          <span class="brand-symbol">
            <span class="brand-cross"></span>
            <span class="brand-wave"></span>
          </span>
        </span>
        <span>
          <strong>Med-Rag</strong>
          <small>医疗知识库助手</small>
        </span>
      </button>

      <nav class="nav-list" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.path"
          type="button"
          class="nav-item"
          :class="{ active: activeRoute === item.path }"
          @click="go(item.path)"
        >
          <span class="nav-icon"><component :is="item.icon" :size="18" /></span>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="sidebar-bottom">
        <div class="sidebar-status">
          <span class="pulse"></span>
          <div>
            <strong>服务可用</strong>
            <small>当前连接本地知识库</small>
          </div>
        </div>
      </div>
    </aside>

    <main class="app-main">
      <header class="app-topbar">
        <div class="topbar-spacer" aria-hidden="true"></div>
        <div class="topbar-actions" aria-label="快捷操作">
          <button class="tool-icon" type="button" @click="toggleTheme" :aria-label="`切换到${theme === 'dark' ? '浅色' : '深色'}主题`" :title="theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'">
            <Moon v-if="theme === 'dark'" :size="17" />
            <Sun v-else :size="17" />
          </button>

        </div>
      </header>
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  BarChart3,
  Clock3,
  Files,
  MessageSquareText,
  Moon,
  Settings,
  Sun,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const theme = ref('dark')
const themeKey = 'med-rag-theme'
const themeTouchedKey = 'med-rag-theme-touched'

const navItems = [
  { path: '/chat', label: '智能问答', icon: MessageSquareText },
  { path: '/documents', label: '文档管理', icon: Files },
  { path: '/history', label: '历史记录', icon: Clock3 },
  { path: '/evaluation', label: '效果评估', icon: BarChart3 },
  { path: '/settings', label: '系统设置', icon: Settings },
]

const activeRoute = computed(() => route.path)

onMounted(() => {
  const saved = window.localStorage.getItem(themeKey)
  const touched = window.localStorage.getItem(themeTouchedKey) === '1'
  if (touched && (saved === 'light' || saved === 'dark')) {
    theme.value = saved
  }
  applyTheme(theme.value)
})

watch(theme, value => {
  applyTheme(value)
  window.localStorage.setItem(themeKey, value)
})

function applyTheme(value) {
  document.documentElement.dataset.theme = value
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  window.localStorage.setItem(themeTouchedKey, '1')
}

function go(path) {
  if (route.path !== path) router.push(path)
}
</script>

<style scoped>
.app-frame {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  background: var(--bg-primary);
}

.app-sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 16px;
  border-right: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 42px;
  padding: 0 0 14px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
  background: transparent;
  text-align: left;
}

.brand-mark {
  position: relative;
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  overflow: hidden;
  border-radius: 13px;
  background:
    radial-gradient(circle at 78% 18%, rgba(255, 255, 255, 0.42), transparent 18px),
    linear-gradient(135deg, #14b8a6 0%, #22c55e 42%, #6366f1 100%);
  box-shadow:
    0 10px 24px rgba(20, 184, 166, 0.22),
    inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}

.brand-aura {
  position: absolute;
  inset: 5px;
  border-radius: 11px;
  background: rgba(15, 17, 23, 0.18);
  box-shadow: inset 0 0 18px rgba(255, 255, 255, 0.12);
}

.brand-symbol {
  position: relative;
  width: 24px;
  height: 24px;
}

.brand-cross,
.brand-cross::before {
  position: absolute;
  content: '';
  border-radius: 999px;
  background: #ffffff;
  box-shadow: 0 1px 8px rgba(255, 255, 255, 0.2);
}

.brand-cross {
  left: 3px;
  top: 9px;
  width: 18px;
  height: 6px;
}

.brand-cross::before {
  left: 6px;
  top: -6px;
  width: 6px;
  height: 18px;
}

.brand-wave {
  position: absolute;
  left: 2px;
  right: 1px;
  bottom: 2px;
  height: 8px;
  border-left: 2px solid rgba(255, 255, 255, 0.9);
  border-bottom: 2px solid rgba(255, 255, 255, 0.9);
  transform: skewX(-24deg);
}

.brand-wave::after {
  position: absolute;
  content: '';
  right: -2px;
  bottom: -2px;
  width: 7px;
  height: 7px;
  border-right: 2px solid rgba(255, 255, 255, 0.9);
  border-top: 2px solid rgba(255, 255, 255, 0.9);
}

.brand strong,
.brand small {
  display: block;
}

.brand strong {
  font-size: 16px;
  line-height: 1.15;
  font-weight: 650;
}

.brand small {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 12px;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 0;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 42px;
  padding: 0 10px;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-weight: 500;
  text-align: left;
  transition: background 0.18s ease, color 0.18s ease;
}

.nav-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.nav-item.active {
  border: 1px solid rgba(99, 102, 241, 0.3);
  background: var(--accent-color-light);
  color: var(--text-primary);
}

.nav-icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  color: var(--text-tertiary);
}

.nav-item.active .nav-icon {
  color: var(--accent-color);
}

.sidebar-bottom {
  margin-top: auto;
  display: grid;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.tool-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
}

.tool-icon:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.sidebar-status {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
}

.sidebar-status strong,
.sidebar-status small {
  display: block;
}

.sidebar-status strong {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.sidebar-status small {
  margin-top: 2px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.pulse {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #22c55e;
}

.app-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-topbar {
  flex: 0 0 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 24px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-primary);
}

.topbar-spacer {
  min-width: 1px;
  min-height: 1px;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 900px) {
  .app-frame {
    grid-template-columns: 1fr;
  }

  .app-sidebar {
    position: static;
    height: auto;
    padding: 14px;
  }

  .nav-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .sidebar-bottom {
    display: none;
  }

  .app-topbar {
    padding: 0 16px;
  }
}
</style>