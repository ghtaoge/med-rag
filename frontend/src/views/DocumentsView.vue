<template>
  <div class="documents-view">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h3>文档管理</h3>
          <div class="header-actions">
            <el-button type="primary" @click="syncAll" :loading="docStore.syncing">
              <el-icon><Refresh /></el-icon> 全量同步
            </el-button>
            <el-upload
              :show-file-list="false"
              :before-upload="handleUpload"
              :disabled="docStore.uploading"
            >
              <el-button type="success" :loading="docStore.uploading">
                <el-icon><Upload /></el-icon> 上传文档
              </el-button>
            </el-upload>
          </div>
        </div>
      </template>

      <!-- 统计信息 -->
      <div class="stats-row">
        <el-statistic title="总文件数" :value="docStore.totalFiles" />
        <el-statistic title="总 Chunk 数" :value="docStore.totalChunks" />
      </div>

      <!-- 文档表格 -->
      <el-table :data="docStore.documents" stripe>
        <el-table-column prop="filename" label="文件名" min-width="200" />
        <el-table-column prop="extension" label="格式" width="80" />
        <el-table-column prop="size" label="大小" width="100">
          <template #default="{ row }">
            {{ formatSize(row.size) }}
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="Chunk 数" width="100" />
        <el-table-column prop="in_index" label="已索引" width="80">
          <template #default="{ row }">
            <el-tag :type="row.in_index ? 'success' : 'info'" size="small">
              {{ row.in_index ? '✓' : '✗' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="syncSingle(row.filename)">同步</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.filename)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDocumentStore } from '../stores/document'
import { syncAllDocuments } from '../services/api'

const docStore = useDocumentStore()

onMounted(() => {
  docStore.loadDocuments()
})

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function handleUpload(file) {
  try {
    const result = await docStore.upload(file)
    if (result.status === 'accepted') {
      ElMessage.success(`文件 ${result.filename} 已入库，${result.chunk_count} 个 chunks`)
    } else {
      ElMessage.warning(`文件被拒绝: ${result.errors.join(', ')}`)
    }
  } catch (e) {
    ElMessage.error('上传失败')
  }
  return false // 阻止默认上传行为
}

async function syncAll() {
  try {
    const result = await docStore.syncAll()
    ElMessage.success(`同步完成，共 ${result.total_chunks} chunks`)
  } catch (e) {
    ElMessage.error('同步失败')
  }
}

async function syncSingle(filename) {
  try {
    const res = await syncAllDocuments() // 使用文档同步 API
    ElMessage.success(`${filename} 同步完成`)
    docStore.loadDocuments()
  } catch (e) {
    ElMessage.error('同步失败')
  }
}

async function handleDelete(filename) {
  try {
    await ElMessageBox.confirm(`确定删除文件 ${filename}？`, '删除确认', {
      type: 'warning',
    })
    await docStore.remove(filename)
    ElMessage.success('已删除')
  } catch (e) {
    // 取消删除
  }
}
</script>

<style scoped>
.documents-view {
  max-width: 900px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.stats-row {
  display: flex;
  gap: 40px;
  margin-bottom: 16px;
}
</style>
