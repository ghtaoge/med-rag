<template>
  <div class="settings-view">
    <el-card shadow="never">
      <template #header>
        <h3>系统设置</h3>
      </template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="系统名称">Med-Rag 知识助手</el-descriptions-item>
        <el-descriptions-item label="版本">v1.0.0</el-descriptions-item>
        <el-descriptions-item label="LLM Provider">{{ engines?.llm_provider || '-' }}</el-descriptions-item>
        <el-descriptions-item label="LLM 模型">{{ engines?.llm_model || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Embedding 模型">{{ engines?.embedding_model || '-' }}</el-descriptions-item>
        <el-descriptions-item label="向量维度">{{ engines?.embedding_dim || '-' }}</el-descriptions-item>
        <el-descriptions-item label="向量库">{{ engines?.vector_store || '-' }}</el-descriptions-item>
        <el-descriptions-item label="关键词库">{{ engines?.keyword_store || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Reranker">{{ engines?.reranker || '-' }}</el-descriptions-item>
        <el-descriptions-item label="混合检索方法">{{ engines?.hybrid_method || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 健康状态 -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <h3 style="margin: 0">健康状态</h3>
          <el-button size="small" @click="checkHealth">
            <el-icon><Refresh /></el-icon> 检查
          </el-button>
        </div>
      </template>

      <el-result
        v-if="health"
        :icon="health.status === 'ok' ? 'success' : 'error'"
        :title="health.status === 'ok' ? '系统运行正常' : '系统异常'"
        :sub-title="`版本: ${health.version || '-'}`"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getEngines, healthCheck } from '../services/api'

const engines = ref(null)
const health = ref(null)

onMounted(async () => {
  try {
    const res = await getEngines()
    engines.value = res.data
  } catch (e) {}

  try {
    const res = await healthCheck()
    health.value = res.data
  } catch (e) {}
})

async function checkHealth() {
  try {
    const res = await healthCheck()
    health.value = res.data
  } catch (e) {
    health.value = { status: 'error' }
  }
}
</script>

<style scoped>
.settings-view {
  max-width: 800px;
}
</style>
