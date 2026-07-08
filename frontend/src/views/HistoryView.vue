<template>
  <div class="history-view">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h3>历史记录</h3>
          <el-button @click="chatStore.loadSessions()">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>

      <el-empty v-if="chatStore.sessions.length === 0" description="暂无历史记录" />

      <div v-else class="session-list">
        <el-card
          v-for="session in chatStore.sessions"
          :key="session.session_id"
          shadow="hover"
          class="session-card"
        >
          <div class="session-content">
            <div class="session-question">
              <el-text tag="b">{{ session.question }}</el-text>
            </div>
            <div class="session-answer">
              <el-text size="small" truncated>{{ session.answer }}</el-text>
            </div>
            <div class="session-meta">
              <el-tag size="small" :type="confidenceType(session.correctness?.confidence)">
                {{ session.correctness?.confidence || '未知' }}
              </el-tag>
              <el-text size="small" type="info">
                {{ session.intent?.category }} · {{ session.correctness?.source_count }} 来源
              </el-text>
              <el-text size="small" type="info">
                {{ formatTime(session.created_at) }}
              </el-text>
            </div>
          </div>
          <div class="session-actions">
            <el-button size="small" type="danger" @click="handleDelete(session.session_id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </el-card>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useChatStore } from '../stores/chat'

const chatStore = useChatStore()

onMounted(() => {
  chatStore.loadSessions()
})

function confidenceType(confidence) {
  if (confidence === 'high') return 'success'
  if (confidence === 'medium') return 'warning'
  return 'danger'
}

function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return d.toLocaleString('zh-CN')
}

async function handleDelete(sessionId) {
  await chatStore.removeSession(sessionId)
  ElMessage.success('已删除')
}
</script>

<style scoped>
.history-view {
  max-width: 800px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-card {
  cursor: pointer;
}

.session-card .el-card__body {
  display: flex;
  justify-content: space-between;
}

.session-content {
  flex: 1;
}

.session-question {
  margin-bottom: 4px;
}

.session-answer {
  margin-bottom: 8px;
}

.session-meta {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
