<template>
  <div class="evaluation-view page-shell">
    <header class="page-header">
      <div>
        <p class="page-subtitle">检查检索、知识库、生成与运行统计，快速判断系统是否具备上线条件。</p>
      </div>
      <button class="btn btn-primary" type="button" :disabled="loadingChecklist" @click="loadChecklist">
        <span class="icon">↻</span>
        {{ loadingChecklist ? '检查中' : '重新检查' }}
      </button>
    </header>

    <section class="panel readiness-card">
      <div class="panel-header">
        <h3 class="panel-title">上线检查清单</h3>
        <span v-if="checklist" class="badge" :class="statusClass(checklist.overall_status)">
          {{ statusLabel(checklist.overall_status) }}
        </span>
      </div>

      <div v-if="checklist" class="panel-body checklist-content">
        <div class="readiness-summary" :class="statusTone(checklist.overall_status)">
          <strong>总体状态：{{ statusLabel(checklist.overall_status) }}</strong>
          <span>{{ checklist.checks?.length || 0 }} 个检查项已返回结果</span>
        </div>

        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>检查项</th>
                <th>状态</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="check in checklist.checks" :key="check.item">
                <td>{{ check.item }}</td>
                <td>
                  <span class="badge" :class="statusClass(check.status)">{{ statusLabel(check.status) }}</span>
                </td>
                <td>{{ check.detail }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else class="empty-state">
        <div>
          <strong>尚未执行检查</strong>
          <span>点击“重新检查”获取当前系统状态。</span>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h3 class="panel-title">运行统计</h3>
        <button class="btn btn-ghost" type="button" @click="loadStats">刷新统计</button>
      </div>
      <div v-if="stats" class="panel-body metrics-grid">
        <div v-for="item in statItems" :key="item.label" class="metric">
          <div class="metric-label">{{ item.label }}</div>
          <div class="metric-value text-value">{{ item.value }}</div>
        </div>
      </div>
      <div v-else class="empty-state">
        <div>
          <strong>暂无统计数据</strong>
          <span>请确认后端评估接口可用。</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getChecklist, getStats } from '../services/api'

const loadingChecklist = ref(false)
const checklist = ref(null)
const stats = ref(null)

const statItems = computed(() => [
  { label: 'Milvus Chunks', value: stats.value?.milvus_chunks ?? '-' },
  { label: '关键词 Chunks', value: stats.value?.keyword_chunks ?? '-' },
  { label: '知识库文件', value: stats.value?.knowledge_files ?? '-' },
  { label: 'QA 会话数', value: stats.value?.qa_sessions ?? '-' },
  { label: 'LLM Provider', value: stats.value?.llm_provider ?? '-' },
  { label: 'Embedding 模型', value: stats.value?.embedding_model ?? '-' },
])

onMounted(() => {
  loadStats()
})

async function loadChecklist() {
  loadingChecklist.value = true
  try {
    const res = await getChecklist()
    checklist.value = res.data
  } catch (e) {
    checklist.value = null
  } finally {
    loadingChecklist.value = false
  }
}

async function loadStats() {
  try {
    const res = await getStats()
    stats.value = res.data
  } catch (e) {
    stats.value = null
  }
}

function statusLabel(status) {
  const map = {
    ok: '正常',
    error: '异常',
    warning: '警告',
    ready: '就绪',
    not_ready: '未就绪',
    partial_ready: '部分就绪',
  }
  return map[status] || status || '未知'
}

function statusClass(status) {
  const map = {
    ok: 'badge-success',
    ready: 'badge-success',
    error: 'badge-danger',
    not_ready: 'badge-danger',
    warning: 'badge-warning',
    partial_ready: 'badge-warning',
  }
  return map[status] || 'badge-info'
}

function statusTone(status) {
  if (['ok', 'ready'].includes(status)) return 'success'
  if (['error', 'not_ready'].includes(status)) return 'error'
  return 'warning'
}
</script>

<style scoped>
.evaluation-view {
  flex: 1;
  max-width: 1100px;
  padding: 34px 44px 48px;
  gap: 22px;
  overflow-y: auto;
}

.page-header {
  align-items: flex-start;
  margin-bottom: 4px;
}


.page-subtitle {
  margin-top: 8px;
}

.readiness-card,
.evaluation-view > .panel {
  width: 100%;
}

.readiness-card .empty-state,
.evaluation-view > .panel .empty-state {
  min-height: 220px;
}

.readiness-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
}

.readiness-summary strong {
  color: var(--text-primary);
}

.readiness-summary span {
  color: var(--text-secondary);
  font-size: 13px;
}

.readiness-summary.success {
  border-color: rgba(34, 197, 94, 0.28);
  background: rgba(34, 197, 94, 0.08);
}

.readiness-summary.warning {
  border-color: rgba(245, 158, 11, 0.28);
  background: rgba(245, 158, 11, 0.08);
}

.readiness-summary.error {
  border-color: rgba(239, 68, 68, 0.28);
  background: rgba(239, 68, 68, 0.08);
}

.text-value {
  font-size: 20px;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .evaluation-view {
    padding: 22px 18px 34px;
  }
}
</style>

