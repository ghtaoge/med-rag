<template>
  <div class="settings-view page-shell">
    <header class="page-header">
      <div>
        <p class="eyebrow">系统配置</p>
        <h2 class="page-title">系统设置</h2>
        <p class="page-subtitle">查看当前模型、检索组件、向量库和健康状态。敏感配置请通过环境变量管理。</p>
      </div>
      <button class="btn btn-ghost" type="button" @click="checkHealth">
        <span class="icon">↻</span>
        检查健康状态
      </button>
    </header>

    <section class="settings-grid">
      <article class="panel system-panel">
        <div class="panel-header">
          <h3 class="panel-title">引擎信息</h3>
          <span class="badge badge-info">v1.0.0</span>
        </div>
        <div class="panel-body info-grid">
          <div v-for="item in engineItems" :key="item.label" class="info-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
      </article>

      <article class="panel health-panel">
        <div class="panel-header">
          <h3 class="panel-title">健康状态</h3>
          <span class="badge" :class="health?.status === 'ok' ? 'badge-success' : 'badge-danger'">
            {{ health?.status === 'ok' ? '运行正常' : '状态未知' }}
          </span>
        </div>
        <div class="panel-body health-body">
          <div class="health-orb" :class="{ ok: health?.status === 'ok' }">
            {{ health?.status === 'ok' ? 'OK' : '!' }}
          </div>
          <div>
            <h3>{{ health?.status === 'ok' ? '系统运行正常' : '系统异常或未连接' }}</h3>
            <p>版本：{{ health?.version || '-' }}</p>
          </div>
        </div>
      </article>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h3 class="panel-title">配置提醒</h3>
      </div>
      <div class="panel-body security-list">
        <div class="notice warning">API Key 应通过 `.env` 或环境变量注入，不要写入前端代码或提交到仓库。</div>
        <div class="notice">生产部署前请修改 MinIO、Redis 等默认凭据，并检查 `docker-compose.yml`。</div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getEngines, healthCheck } from '../services/api'

const engines = ref(null)
const health = ref(null)

const engineItems = computed(() => [
  { label: '系统名称', value: 'Med-Rag 知识助手' },
  { label: 'LLM Provider', value: engines.value?.llm_provider || '-' },
  { label: 'LLM 模型', value: engines.value?.llm_model || '-' },
  { label: 'Embedding 模型', value: engines.value?.embedding_model || '-' },
  { label: '向量维度', value: engines.value?.embedding_dim || '-' },
  { label: '向量库', value: engines.value?.vector_store || '-' },
  { label: '关键词库', value: engines.value?.keyword_store || '-' },
  { label: 'Reranker', value: engines.value?.reranker || '-' },
  { label: '混合检索方法', value: engines.value?.hybrid_method || '-' },
])

onMounted(async () => {
  try {
    const res = await getEngines()
    engines.value = res.data
  } catch (e) {}

  await checkHealth()
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
  flex: 1;
  overflow-y: auto;
  padding: 34px 44px 48px;
  max-width: none;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  gap: 16px;
  max-width: 980px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.info-item {
  min-height: 74px;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
}

.info-item span,
.info-item strong {
  display: block;
}

.info-item span {
  color: var(--text-secondary);
  font-size: 12px;
}

.info-item strong {
  margin-top: 8px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.health-body {
  display: flex;
  align-items: center;
  gap: 16px;
}

.health-orb {
  display: grid;
  place-items: center;
  width: 82px;
  height: 82px;
  flex: 0 0 82px;
  border-radius: 50%;
  background: rgba(239, 68, 68, 0.12);
  color: var(--red);
  font-size: 24px;
  font-weight: 700;
}

.health-orb.ok {
  background: var(--accent-color-light);
  color: var(--accent-color);
}

.health-body h3 {
  margin: 0 0 8px;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 600;
}

.health-body p {
  margin: 0;
  color: var(--text-secondary);
}

.security-list {
  display: grid;
  gap: 10px;
}

@media (max-width: 900px) {
  .settings-view {
    padding: 22px 18px 34px;
  }

  .settings-grid,
  .info-grid {
    grid-template-columns: 1fr;
  }
}
</style>

