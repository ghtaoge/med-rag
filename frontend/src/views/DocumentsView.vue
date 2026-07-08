<template>
  <div class="documents-view page-shell">
    <header class="page-header document-header">
      <div>
        <p class="eyebrow">文档中心</p>
        <h2 class="page-title">文档管理</h2>
        <p class="page-subtitle">查看已上传文件、同步索引状态，并按单个文件写入向量数据库。</p>
      </div>
      <div class="toolbar">
        <button class="btn btn-ghost" type="button" @click="refreshDocuments">
          <RefreshCw :size="16" />
          刷新
        </button>
        <button class="btn btn-primary" type="button" :disabled="docStore.syncing" @click="syncAll">
          <Database :size="16" />
          {{ docStore.syncing ? '同步中' : '全量同步' }}
        </button>
        <label class="btn btn-success upload-button" :class="{ disabled: docStore.uploading }">
          <FileUp :size="16" />
          {{ docStore.uploading ? '上传中' : '上传文档' }}
          <input type="file" :disabled="docStore.uploading" @change="handleFileChange" />
        </label>
      </div>
    </header>

    <section class="metrics-grid document-metrics">
      <div class="metric">
        <div class="metric-label">总文件数</div>
        <div class="metric-value">{{ docStore.totalFiles }}</div>
      </div>
      <div class="metric">
        <div class="metric-label">已入库 Chunk</div>
        <div class="metric-value">{{ docStore.totalChunks }}</div>
      </div>
      <div class="metric">
        <div class="metric-label">已索引文件</div>
        <div class="metric-value">{{ indexedCount }}</div>
      </div>
      <div class="metric">
        <div class="metric-label">待同步文件</div>
        <div class="metric-value">{{ pendingCount }}</div>
      </div>
    </section>

    <div v-if="notice" class="notice" :class="notice.type">{{ notice.text }}</div>

    <section class="panel file-manager">
      <div class="panel-header file-manager-header">
        <div class="file-manager-title">
          <h3 class="panel-title">已上传文件</h3>
          <p>显示 {{ filteredDocuments.length }} / {{ docStore.documents.length }} 个文件</p>
        </div>
        <div class="manager-tools">
          <label class="search-box" aria-label="搜索文件">
            <Search :size="16" />
            <input v-model="keyword" type="search" placeholder="搜索文件名或格式" />
          </label>

          <div class="filter-menu">
            <button
              class="filter-trigger"
              type="button"
              aria-haspopup="listbox"
              :aria-expanded="filterOpen"
              @click="filterOpen = !filterOpen"
            >
              <ListFilter :size="16" />
              <span>{{ activeStatusLabel }}</span>
              <ChevronDown :size="15" class="filter-chevron" :class="{ open: filterOpen }" />
            </button>
            <div v-if="filterOpen" class="filter-options" role="listbox" aria-label="筛选索引状态">
              <button
                v-for="option in statusOptions"
                :key="option.value"
                type="button"
                class="filter-option"
                :class="{ active: statusFilter === option.value }"
                role="option"
                :aria-selected="statusFilter === option.value"
                @click="selectStatus(option.value)"
              >
                <span>{{ option.label }}</span>
                <Check v-if="statusFilter === option.value" :size="14" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="docStore.documents.length && filteredDocuments.length" class="table-section">
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>文件</th>
                <th>格式</th>
                <th>大小</th>
                <th>Chunk</th>
                <th>索引状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="doc in pagedDocuments" :key="doc.filename">
                <td>
                  <div class="file-cell">
                    <span class="file-icon"><FileText :size="18" /></span>
                    <div class="file-meta">
                      <strong>{{ doc.filename }}</strong>
                      <span>{{ doc.in_index ? '已进入检索链路' : '尚未写入向量库' }}</span>
                    </div>
                  </div>
                </td>
                <td><span class="badge">{{ extensionLabel(doc.extension) }}</span></td>
                <td>{{ formatSize(doc.size) }}</td>
                <td>{{ doc.chunk_count }}</td>
                <td>
                  <span class="badge" :class="doc.in_index ? 'badge-success' : 'badge-warning'">
                    {{ doc.in_index ? '已索引' : '待同步' }}
                  </span>
                </td>
                <td>
                  <div class="row-actions">
                    <button
                      class="mini-button"
                      type="button"
                      :disabled="syncingFile === doc.filename || docStore.syncing"
                      @click="syncSingle(doc.filename)"
                    >
                      <Database :size="14" />
                      {{ syncingFile === doc.filename ? '同步中' : '单文件同步' }}
                    </button>
                    <button class="mini-button danger" type="button" @click="handleDelete(doc.filename)">
                      <Trash2 :size="14" />
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <footer class="pagination-bar" aria-label="文件分页">
          <span>显示 {{ pageStart }}-{{ pageEnd }} / {{ filteredDocuments.length }} 个文件</span>
          <div class="pagination-actions">
            <button class="pager-button" type="button" :disabled="currentPage === 1" title="第一页" @click="goToPage(1)">
              <ChevronsLeft :size="15" />
            </button>
            <button class="pager-button" type="button" :disabled="currentPage === 1" title="上一页" @click="goToPage(currentPage - 1)">
              <ChevronLeft :size="15" />
            </button>
            <button
              v-for="page in pageButtons"
              :key="page"
              class="pager-button number"
              type="button"
              :class="{ active: currentPage === page }"
              @click="goToPage(page)"
            >
              {{ page }}
            </button>
            <button class="pager-button" type="button" :disabled="currentPage === totalPages" title="下一页" @click="goToPage(currentPage + 1)">
              <ChevronRight :size="15" />
            </button>
            <button class="pager-button" type="button" :disabled="currentPage === totalPages" title="最后一页" @click="goToPage(totalPages)">
              <ChevronsRight :size="15" />
            </button>
          </div>
        </footer>
      </div>

      <div v-else-if="docStore.documents.length" class="empty-state compact-empty">
        <div>
          <strong>没有匹配文件</strong>
          <span>换一个关键词，或切回“全部状态”。</span>
        </div>
      </div>

      <div v-else class="empty-state upload-empty">
        <div>
          <span class="empty-icon"><FolderOpen :size="28" /></span>
          <strong>还没有文档</strong>
          <span>上传 TXT、MD、PDF、DOCX、图片或表格后，系统会自动同步；也可以在列表里单独重建某个文件索引。</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useDocumentStore } from '../stores/document'
import { syncSingleDocument } from '../services/api'
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Database,
  FileText,
  FileUp,
  FolderOpen,
  ListFilter,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-vue-next'

const docStore = useDocumentStore()
const notice = ref(null)
const keyword = ref('')
const statusFilter = ref('all')
const filterOpen = ref(false)
const syncingFile = ref('')
const currentPage = ref(1)
const pageSize = 8

const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'indexed', label: '已索引' },
  { value: 'pending', label: '待同步' },
]

const indexedCount = computed(() => docStore.documents.filter(doc => doc.in_index).length)
const pendingCount = computed(() => docStore.documents.filter(doc => !doc.in_index).length)
const activeStatusLabel = computed(() => statusOptions.find(option => option.value === statusFilter.value)?.label || '全部状态')

const filteredDocuments = computed(() => {
  const term = keyword.value.trim().toLowerCase()
  return docStore.documents.filter(doc => {
    const matchesStatus =
      statusFilter.value === 'all' ||
      (statusFilter.value === 'indexed' && doc.in_index) ||
      (statusFilter.value === 'pending' && !doc.in_index)
    const matchesKeyword =
      !term ||
      doc.filename.toLowerCase().includes(term) ||
      (doc.extension || '').toLowerCase().includes(term)
    return matchesStatus && matchesKeyword
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredDocuments.value.length / pageSize)))
const pageStart = computed(() => (filteredDocuments.value.length ? (currentPage.value - 1) * pageSize + 1 : 0))
const pageEnd = computed(() => Math.min(currentPage.value * pageSize, filteredDocuments.value.length))

const pagedDocuments = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredDocuments.value.slice(start, start + pageSize)
})

const pageButtons = computed(() => {
  const maxButtons = 5
  const total = totalPages.value
  let start = Math.max(1, currentPage.value - 2)
  let end = Math.min(total, start + maxButtons - 1)
  start = Math.max(1, end - maxButtons + 1)
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
})

watch([keyword, statusFilter], () => {
  currentPage.value = 1
})

watch(totalPages, pages => {
  if (currentPage.value > pages) currentPage.value = pages
})

onMounted(() => {
  refreshDocuments()
})

function showNotice(type, text) {
  notice.value = { type, text }
  window.setTimeout(() => {
    if (notice.value?.text === text) notice.value = null
  }, 3600)
}

function selectStatus(value) {
  statusFilter.value = value
  filterOpen.value = false
}

function goToPage(page) {
  currentPage.value = Math.min(Math.max(1, page), totalPages.value)
}

function formatSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function extensionLabel(extension = '') {
  const normalized = extension.replace('.', '').toUpperCase()
  return normalized || '-'
}

async function refreshDocuments() {
  await docStore.loadDocuments()
}

async function handleFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return

  try {
    const result = await docStore.upload(file)
    if (result.status === 'accepted') {
      showNotice('success', `文件 ${result.filename} 已入库，生成 ${result.chunk_count} 个 chunks`)
    } else {
      showNotice('warning', `文件被拒绝：${(result.errors || []).join('、')}`)
    }
  } catch (e) {
    showNotice('error', '上传失败，请检查文件格式或后端服务状态')
  }
}

async function syncAll() {
  try {
    const result = await docStore.syncAll()
    showNotice('success', `全量同步完成，共 ${result.total_chunks} 个 chunks`)
  } catch (e) {
    showNotice('error', '同步失败，请检查 Milvus、Redis 或后端日志')
  }
}

async function syncSingle(filename) {
  syncingFile.value = filename
  try {
    const res = await syncSingleDocument(filename)
    showNotice('success', `${filename} 已同步到向量数据库，生成 ${res.data.chunk_count} 个 chunks`)
    await docStore.loadDocuments()
  } catch (e) {
    showNotice('error', `${filename} 同步失败`)
  } finally {
    syncingFile.value = ''
  }
}

async function handleDelete(filename) {
  if (!window.confirm(`确定删除文件 ${filename}？`)) return
  try {
    await docStore.remove(filename)
    showNotice('success', `${filename} 已删除`)
  } catch (e) {
    showNotice('error', `${filename} 删除失败`)
  }
}
</script>

<style scoped>
.documents-view {
  flex: 1;
  max-width: 1100px;
  overflow-y: auto;
  padding: 34px 44px 48px;
}

.document-header,
.document-metrics,
.file-manager {
  width: 100%;
}

.document-metrics {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.upload-button {
  position: relative;
  overflow: hidden;
}

.upload-button input {
  position: absolute;
  inset: 0;
  opacity: 0;
  pointer-events: none;
}

.upload-button:not(.disabled) input {
  pointer-events: auto;
}

.upload-button.disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.file-manager-header {
  align-items: center;
}

.file-manager-title p {
  margin: 3px 0 0;
  color: var(--text-tertiary);
  font-size: 12px;
}

.manager-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.search-box,
.filter-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-tertiary);
}

.search-box input {
  min-width: 160px;
  border: 0;
  outline: 0;
  color: var(--text-primary);
  background: transparent;
}

.filter-menu {
  position: relative;
}

.filter-trigger {
  min-width: 150px;
  justify-content: space-between;
  color: var(--text-secondary);
}

.filter-trigger span {
  color: var(--text-primary);
  font-size: 13px;
}

.filter-chevron {
  transition: transform 0.16s ease;
}

.filter-chevron.open {
  transform: rotate(180deg);
}

.filter-options {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 30;
  min-width: 150px;
  padding: 6px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  box-shadow: 0 18px 34px rgba(0, 0, 0, 0.28);
}

.filter-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 32px;
  padding: 0 8px;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  text-align: left;
}

.filter-option:hover,
.filter-option.active {
  background: var(--accent-color-light);
  color: var(--text-primary);
}

.table-section {
  display: flex;
  flex-direction: column;
}

.file-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 280px;
}

.file-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  border-radius: 8px;
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.file-meta strong,
.file-meta span {
  display: block;
}

.file-meta strong {
  max-width: 360px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta span {
  margin-top: 2px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.row-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.mini-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--bg-primary);
  color: var(--primary-strong);
  font-size: 12px;
  font-weight: 500;
}

.mini-button:hover:not(:disabled) {
  background: var(--bg-tertiary);
}

.mini-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.mini-button.danger {
  border-color: rgba(239, 68, 68, 0.28);
  background: rgba(239, 68, 68, 0.08);
  color: var(--red);
}

.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 50px;
  padding: 10px 14px;
  border-top: 1px solid var(--border-color);
  color: var(--text-tertiary);
  font-size: 12px;
}

.pagination-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pager-button {
  display: grid;
  place-items: center;
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
}

.pager-button:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.pager-button.active {
  border-color: rgba(99, 102, 241, 0.35);
  background: var(--accent-color-light);
  color: var(--text-primary);
}

.pager-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.upload-empty {
  min-height: 280px;
}

.compact-empty {
  min-height: 180px;
}

.empty-icon {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  margin: 0 auto 12px;
  border-radius: 12px;
  background: var(--primary-soft);
  color: var(--primary-strong);
}

@media (max-width: 980px) {
  .documents-view {
    padding: 22px 18px 34px;
  }

  .document-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .file-manager-header {
    align-items: stretch;
    flex-direction: column;
  }

  .manager-tools,
  .search-box,
  .filter-menu,
  .filter-trigger {
    width: 100%;
  }

  .search-box input {
    width: 100%;
  }

  .filter-options {
    left: 0;
    right: auto;
    width: 100%;
  }

  .pagination-bar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>