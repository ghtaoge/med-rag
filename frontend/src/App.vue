<template>
  <router-view v-if="route.meta.public" />
  <div
    v-else
    class="app-frame"
    :class="{ 'sidebar-collapsed': isSidebarCollapsed, 'sidebar-resizing': isSidebarResizing }"
    :data-theme="theme"
    :style="frameStyle"
  >
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
      <button
        class="sidebar-toggle"
        type="button"
        :aria-label="isSidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
        :title="isSidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="toggleSidebar"
      >
        <PanelLeftOpen v-if="isSidebarCollapsed" :size="17" />
        <PanelLeftClose v-else :size="17" />
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
          <span class="nav-label">{{ item.label }}</span>
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
      <div
        v-if="!isSidebarCollapsed"
        class="sidebar-resizer"
        role="separator"
        aria-orientation="vertical"
        title="拖动调整侧边栏宽度"
        @pointerdown="startSidebarResize"
      ></div>
    </aside>

    <main class="app-main">
      <header class="app-topbar">
        <div class="topbar-spacer" aria-hidden="true"></div>
        <div class="topbar-actions" aria-label="快捷操作">
          <button class="tool-icon" type="button" @click="toggleTheme" :aria-label="`切换到${theme === 'dark' ? '浅色' : '深色'}主题`" :title="theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'">
            <Moon v-if="theme === 'dark'" :size="17" />
            <Sun v-else :size="17" />
          </button>

          <span class="account-name">{{ auth.user?.username }}</span>
          <button class="tool-icon" type="button" aria-label="退出登录" title="退出登录" @click="handleLogout">
            <LogOut :size="17" />
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
  LogOut,
  MessageSquareText,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sun,
} from 'lucide-vue-next'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const theme = ref('dark')
const themeKey = 'med-rag-theme'
const themeTouchedKey = 'med-rag-theme-touched'
const sidebarWidthKey = 'med-rag-sidebar-width'
const sidebarCollapsedKey = 'med-rag-sidebar-collapsed'
const sidebarWidth = ref(280)
const isSidebarCollapsed = ref(false)
const isSidebarResizing = ref(false)
// 侧边栏宽度限制要和 CSS 网格配合：太窄会挤压导航文字，太宽会侵占问答区。
const minSidebarWidth = 220
const maxSidebarWidth = 420
const collapsedSidebarWidth = 72

const allNavItems = [
  { path: '/chat', label: '智能问答', icon: MessageSquareText, permission: 'chat' },
  { path: '/documents', label: '文档管理', icon: Files, permission: 'document_read' },
  { path: '/history', label: '历史记录', icon: Clock3, permission: 'chat' },
  { path: '/evaluation', label: '效果评估', icon: BarChart3, permission: 'platform_config' },
  { path: '/settings', label: '系统设置', icon: Settings, permission: 'platform_config' },
]
const navItems = computed(() => allNavItems.filter(item => auth.hasPermission(item.permission)))

const activeRoute = computed(() => route.path)
const frameStyle = computed(() => ({
  '--sidebar-width': `${isSidebarCollapsed.value ? collapsedSidebarWidth : sidebarWidth.value}px`,
}))

onMounted(() => {
  // 主题只有在用户主动切换过后才从 localStorage 恢复，
  // 避免首次打开页面时被旧浏览器残留值影响默认暗色体验。
  const saved = window.localStorage.getItem(themeKey)
  const touched = window.localStorage.getItem(themeTouchedKey) === '1'
  if (touched && (saved === 'light' || saved === 'dark')) {
    theme.value = saved
  }
  // 恢复上次拖拽后的宽度，并重新 clamp 一次，防止未来调整 min/max 后出现异常布局。
  const savedWidthValue = window.localStorage.getItem(sidebarWidthKey)
  if (savedWidthValue !== null) {
    const savedWidth = Number(savedWidthValue)
    if (Number.isFinite(savedWidth)) {
      sidebarWidth.value = clampSidebarWidth(savedWidth)
    }
  }
  isSidebarCollapsed.value = window.localStorage.getItem(sidebarCollapsedKey) === '1'
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

async function handleLogout() {
  await auth.logout()
  await router.replace('/login')
}

function clampSidebarWidth(value) {
  return Math.min(maxSidebarWidth, Math.max(minSidebarWidth, Math.round(value)))
}

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  window.localStorage.setItem(sidebarCollapsedKey, isSidebarCollapsed.value ? '1' : '0')
}

function startSidebarResize(event) {
  if (isSidebarCollapsed.value) return
  event.preventDefault()
  isSidebarResizing.value = true

  // 记录拖拽起点，后续只用鼠标位移计算宽度，避免连续赋值带来的累计误差。
  const startX = event.clientX
  const startWidth = sidebarWidth.value

  const handleMove = (moveEvent) => {
    sidebarWidth.value = clampSidebarWidth(startWidth + moveEvent.clientX - startX)
  }

  const handleUp = () => {
    isSidebarResizing.value = false
    // 只在拖拽结束时持久化，移动过程中保持 UI 响应即可，减少频繁写 localStorage。
    window.localStorage.setItem(sidebarWidthKey, String(sidebarWidth.value))
    window.removeEventListener('pointermove', handleMove)
    window.removeEventListener('pointerup', handleUp)
    window.removeEventListener('pointercancel', handleUp)
  }

  window.addEventListener('pointermove', handleMove)
  window.addEventListener('pointerup', handleUp)
  window.addEventListener('pointercancel', handleUp)
}
</script>

<style scoped>
.app-frame {
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--sidebar-width, 280px) minmax(0, 1fr);
  background: var(--bg-primary);
  transition: grid-template-columns 0.18s ease;
}

.app-frame.sidebar-resizing {
  cursor: col-resize;
  user-select: none;
  transition: none;
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
  overflow: visible;
  transition: padding 0.18s ease;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  width: calc(100% - 40px);
  min-height: 42px;
  padding: 0 0 14px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
  background: transparent;
  text-align: left;
}

.sidebar-toggle {
  position: absolute;
  top: 16px;
  right: 12px;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
}

.sidebar-toggle:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.account-name {
  max-width: 180px;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.nav-label,
.brand > span:last-child,
.sidebar-status div {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
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

.sidebar-resizer {
  position: absolute;
  top: 0;
  right: -4px;
  width: 8px;
  height: 100%;
  cursor: col-resize;
  touch-action: none;
}

.sidebar-resizer::after {
  position: absolute;
  content: '';
  top: 0;
  left: 3px;
  width: 2px;
  height: 100%;
  background: transparent;
  transition: background 0.18s ease;
}

.sidebar-resizer:hover::after,
.sidebar-resizing .sidebar-resizer::after {
  background: var(--accent-color);
}

.sidebar-collapsed .app-sidebar {
  align-items: center;
  padding: 16px 10px;
}

.sidebar-collapsed .brand {
  width: 100%;
  justify-content: center;
  padding-bottom: 12px;
}

.sidebar-collapsed .brand > span:last-child,
.sidebar-collapsed .nav-label,
.sidebar-collapsed .sidebar-bottom {
  display: none;
}

.sidebar-collapsed .sidebar-toggle {
  position: static;
  margin-top: 8px;
}

.sidebar-collapsed .nav-list {
  width: 100%;
}

.sidebar-collapsed .nav-item {
  justify-content: center;
  padding: 0;
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
