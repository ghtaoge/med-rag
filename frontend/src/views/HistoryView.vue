<template>
  <div class="history-view page-shell">
    <header class="page-header">
      <div>
        <p class="eyebrow">Session Archive</p>
        <h2 class="page-title">历史记录</h2>
        <p class="page-subtitle">查看最近问答、置信度和引用数量，便于复盘知识库回答质量。</p>
      </div>
      <button class="btn btn-ghost" type="button" @click="chatStore.loadSessions()">
        <span class="icon">↻</span>
        刷新
      </button>
    </header>

    <div v-if="notice" class="notice success">{{ notice }}</div>

    <section class="panel">
      <div v-if="chatStore.sessions.length" class="session-list panel-body">
        <article v-for="session in chatStore.sessions" :key="session.session_id" class="session-card">
          <div class="session-main">
            <div class="session-topline">
              <span class="badge" :class="confidenceClass(session.correctness?.confidence)">
                {{ confidenceLabel(session.correctness?.confidence) }}
              </span>
              <span class="session-time">{{ formatTime(session.created_at) }}</span>
            </div>
            <h3>{{ session.question }}</h3>
            <p>{{ session.answer || '暂无回答内容' }}</p>
            <div class="session-meta">
              <span>{{ intentLabel(session.intent?.category) }}</span>
              <span>{{ session.correctness?.source_count || 0 }} 个来源</span>
              <span>{{ session.session_id }}</span>
            </div>
          </div>
          <button class="delete-button" type="button" aria-label="删除记录" @click="handleDelete(session.session_id)">
            ×
          </button>
        </article>
      </div>

      <div v-else class="empty-state">
        <div>
          <strong>暂无历史记录</strong>
          <span>完成一次问答后，会话会显示在这里。</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useChatStore } from '../stores/chat'

const chatStore = useChatStore()
const notice = ref('')

onMounted(() => {
  chatStore.loadSessions()
})

function confidenceLabel(confidence) {
  if (confidence === 'high') return '高置信度'
  if (confidence === 'medium') return '中置信度'
  if (confidence === 'low') return '低置信度'
  return '未知置信度'
}

function confidenceClass(confidence) {
  if (confidence === 'high') return 'badge-success'
  if (confidence === 'medium') return 'badge-warning'
  if (confidence === 'low') return 'badge-danger'
  return 'badge-info'
}

function intentLabel(category) {
  const map = { query: '查询', definition: '定义', comparison: '对比', process: '流程', negation: '否定' }
  return map[category] || '未分类'
}

function formatTime(isoStr) {
  if (!isoStr) return '时间未知'
  return new Date(isoStr).toLocaleString('zh-CN')
}

async function handleDelete(sessionId) {
  if (!window.confirm('确定删除这条历史记录？')) return
  await chatStore.removeSession(sessionId)
  notice.value = '已删除'
  window.setTimeout(() => {
    notice.value = ''
  }, 2200)
}
</script>

<style scoped>
.history-view {
  flex: 1;
  max-width: 1060px;
  overflow-y: auto;
  padding: 34px 44px 48px;
}

.session-list {
  display: grid;
  gap: 12px;
}

.session-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-strong);
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}

.session-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 30px rgba(31, 45, 62, 0.1);
}

.session-topline,
.session-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.session-time {
  color: var(--muted);
  font-size: 12px;
}

.session-card h3 {
  margin: 10px 0 8px;
  color: var(--ink);
  font-size: 16px;
  line-height: 1.45;
}

.session-card p {
  display: -webkit-box;
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.session-meta {
  margin-top: 12px;
  color: var(--faint);
  font-size: 12px;
}

.delete-button {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: rgba(240, 123, 123, 0.12);
  color: var(--red);
  font-size: 22px;
  line-height: 1;
}

@media (max-width: 900px) {
  .history-view {
    padding: 22px 18px 34px;
  }
}
</style>

