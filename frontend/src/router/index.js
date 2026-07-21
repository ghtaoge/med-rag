import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', redirect: '/chat' },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/ChatView.vue'),
    meta: { permission: 'chat' },
  },
  {
    path: '/documents',
    name: 'Documents',
    component: () => import('../views/DocumentsView.vue'),
    meta: { permission: 'document_read' },
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/HistoryView.vue'),
    meta: { permission: 'chat' },
  },
  {
    path: '/evaluation',
    name: 'Evaluation',
    component: () => import('../views/EvaluationView.vue'),
    meta: { permission: 'platform_config' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { permission: 'platform_config' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

function firstAllowedRoute(auth) {
  return routes.find(route => route.meta?.permission && auth.hasPermission(route.meta.permission))?.path || '/login'
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.initialize()
  if (to.meta.public) {
    return auth.isAuthenticated ? firstAllowedRoute(auth) : true
  }
  if (!auth.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.permission && !auth.hasPermission(to.meta.permission)) {
    return firstAllowedRoute(auth)
  }
  return true
})

export default router
