<template>
  <div class="evaluation-view">
    <!-- 上线检查清单 -->
    <el-card shadow="never" class="eval-card">
      <template #header>
        <div class="card-header">
          <h3>上线检查清单</h3>
          <el-button @click="loadChecklist" :loading="loadingChecklist">
            <el-icon><Refresh /></el-icon> 重新检查
          </el-button>
        </div>
      </template>

      <div v-if="checklist" class="checklist-content">
        <el-alert
          :title="`总体状态: ${statusLabel(checklist.overall_status)}`"
          :type="statusType(checklist.overall_status)"
          :closable="false"
          show-icon
          class="overall-status"
        />

        <el-table :data="checklist.checks" stripe>
          <el-table-column prop="item" label="检查项" width="160" />
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="详情" />
        </el-table>
      </div>

      <el-empty v-else description="点击 重新检查 查看系统状态" />
    </el-card>

    <!-- 运行统计 -->
    <el-card shadow="never" class="eval-card">
      <template #header>
        <h3>运行统计</h3>
      </template>

      <div v-if="stats" class="stats-grid">
        <el-statistic title="Milvus Chunks" :value="stats.milvus_chunks" />
        <el-statistic title="关键词 Chunks" :value="stats.keyword_chunks" />
        <el-statistic title="知识库文件" :value="stats.knowledge_files" />
        <el-statistic title="QA 会话数" :value="stats.qa_sessions" />
        <el-statistic title="LLM Provider" :value="stats.llm_provider" />
        <el-statistic title="Embedding 模型" :value="stats.embedding_model" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getChecklist, getStats } from '../services/api'

const loadingChecklist = ref(false)
const checklist = ref(null)
const stats = ref(null)

onMounted(async () => {
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
  const map = { ok: '✅ 正常', error: '❌ 异常', warning: '⚠️ 警告', ready: '✅ 就绪', not_ready: '❌ 未就绪', partial_ready: '⚠️ 部分' }
  return map[status] || status
}

function statusType(status) {
  const map = { ok: 'success', error: 'danger', warning: 'warning', ready: 'success', not_ready: 'danger', partial_ready: 'warning' }
  return map[status] || 'info'
}
</script>

<style scoped>
.evaluation-view {
  max-width: 900px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.eval-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.eval-card .card-header h3 {
  margin: 0;
}

.overall-status {
  margin-bottom: 16px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
</style>
