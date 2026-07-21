<template>
  <div class="documents-view page-shell">
    <header class="page-header">
      <div>
        <h1 class="page-title">知识文档</h1>
        <p class="page-subtitle">文档经过草稿、审核和批准后才会进入检索索引。</p>
      </div>
      <button class="btn btn-ghost" type="button" @click="refresh">
        <RefreshCw :size="16" />
        刷新
      </button>
    </header>

    <section v-if="canEdit" class="upload-band" aria-label="上传文档">
      <label>
        <span>归属部门</span>
        <select v-model="ownerDepartmentId">
          <option v-for="id in auth.editableDepartments" :key="id" :value="id">{{ id }}</option>
        </select>
      </label>
      <label>
        <span>可见范围</span>
        <select v-model="visibility">
          <option value="department_only">仅归属部门</option>
          <option value="shared_departments">指定部门共享</option>
        </select>
      </label>
      <label v-if="visibility === 'shared_departments'" class="shared-input">
        <span>共享部门 ID</span>
        <input v-model="sharedDepartments" placeholder="多个 ID 用逗号分隔" />
      </label>
      <label class="btn btn-primary upload-button" :class="{ disabled: docStore.uploading }">
        <FileUp :size="16" />
        {{ docStore.uploading ? '上传中' : '选择文件' }}
        <input type="file" :disabled="docStore.uploading" @change="upload" />
      </label>
    </section>

    <div v-if="notice" class="notice" :class="notice.type">{{ notice.text }}</div>

    <section class="metrics-grid document-metrics">
      <div class="metric"><div class="metric-label">全部</div><div class="metric-value">{{ docStore.totalFiles }}</div></div>
      <div class="metric"><div class="metric-label">草稿</div><div class="metric-value">{{ statusCount('draft') }}</div></div>
      <div class="metric"><div class="metric-label">审核中</div><div class="metric-value">{{ statusCount('in_review') }}</div></div>
      <div class="metric"><div class="metric-label">已批准</div><div class="metric-value">{{ statusCount('approved') }}</div></div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2 class="panel-title">文档版本</h2>
        <label class="search-box">
          <Search :size="16" />
          <input v-model.trim="keyword" type="search" placeholder="搜索文件名" />
        </label>
      </div>
      <div v-if="filteredDocuments.length" class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>文档</th>
              <th>归属部门</th>
              <th>版本</th>
              <th>状态</th>
              <th>隔离处理</th>
              <th>审核人</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="doc in filteredDocuments" :key="doc.document_id">
              <td>
                <div class="file-cell">
                  <FileText :size="18" />
                  <div><strong>{{ doc.display_name }}</strong><small>{{ formatSize(doc.size) }}</small></div>
                </div>
              </td>
              <td><code>{{ shortId(doc.owner_department_id) }}</code></td>
              <td>v{{ doc.version_number }}</td>
              <td><span class="badge" :class="statusClass(doc.status)">{{ statusLabel(doc.status) }}</span></td>
              <td>
                <span class="badge" :class="processingClass(doc.processing_status)">
                  {{ processingLabel(doc.processing_status) }}
                </span>
              </td>
              <td>{{ doc.reviewed_by ? shortId(doc.reviewed_by) : '-' }}</td>
              <td>
                <div class="row-actions">
                  <button
                    v-if="doc.status === 'draft' && doc.processing_status === 'ready_for_review' && canEditDepartment(doc.owner_department_id)"
                    class="mini-button"
                    type="button"
                    :disabled="isWorking(doc)"
                    @click="submitReview(doc)"
                  ><Send :size="14" />提交审核</button>
                  <button
                    v-if="doc.status === 'in_review' && canApproveDepartment(doc.owner_department_id)"
                    class="mini-button success"
                    type="button"
                    :disabled="isWorking(doc)"
                    @click="approve(doc)"
                  ><BadgeCheck :size="14" />批准</button>
                  <button
                    v-if="doc.status === 'approved' && canEditDepartment(doc.owner_department_id)"
                    class="mini-button"
                    type="button"
                    :disabled="isWorking(doc)"
                    @click="sync(doc)"
                  ><Database :size="14" />重建索引</button>
                  <button
                    v-if="doc.status === 'approved' && canApproveDepartment(doc.owner_department_id)"
                    class="mini-button danger"
                    type="button"
                    :disabled="isWorking(doc)"
                    @click="revoke(doc)"
                  ><Ban :size="14" />撤回</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state"><div><strong>暂无文档</strong><span>当前可见范围内没有匹配记录。</span></div></div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  BadgeCheck,
  Ban,
  Database,
  FileText,
  FileUp,
  RefreshCw,
  Search,
  Send,
} from 'lucide-vue-next'

import { useAuthStore } from '../stores/auth'
import { useDocumentStore } from '../stores/document'

const auth = useAuthStore()
const docStore = useDocumentStore()
const keyword = ref('')
const notice = ref(null)
const ownerDepartmentId = ref(auth.editableDepartments[0] || '')
const visibility = ref('department_only')
const sharedDepartments = ref('')
const canEdit = computed(() => auth.hasPermission('document_edit'))
const filteredDocuments = computed(() => {
  const term = keyword.value.toLowerCase()
  return docStore.documents.filter(doc => !term || doc.display_name.toLowerCase().includes(term))
})

onMounted(refresh)
onUnmounted(() => docStore.stopPolling())

function membershipsFor(departmentId) {
  return (auth.user?.memberships || []).filter(item => item.department_id === departmentId)
}

function canEditDepartment(departmentId) {
  return membershipsFor(departmentId).some(item => item.role === 'knowledge_editor')
}

function canApproveDepartment(departmentId) {
  return membershipsFor(departmentId).some(item => item.role === 'knowledge_reviewer')
}

function statusCount(status) {
  return docStore.documents.filter(doc => doc.status === status).length
}

function statusLabel(status) {
  return { draft: '草稿', in_review: '审核中', approved: '已批准', revoked: '已撤回', expired: '已过期' }[status] || status
}

function statusClass(status) {
  return { approved: 'badge-success', in_review: 'badge-warning', revoked: 'badge-danger' }[status] || 'badge-info'
}

function processingLabel(status) {
  return {
    quarantined: '隔离检查中',
    scanning: '安全扫描中',
    parsing: '解析中',
    ready_for_review: '待审核',
    infected: '检测到风险',
    failed: '处理失败',
  }[status] || '等待处理'
}

function processingClass(status) {
  if (status === 'ready_for_review') return 'badge-success'
  if (status === 'infected' || status === 'failed') return 'badge-danger'
  return 'badge-warning'
}

function shortId(value = '') {
  return value.length > 12 ? `${value.slice(0, 8)}...` : value
}

function formatSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function isWorking(doc) {
  return docStore.workingDocumentId === doc.document_id
}

function show(type, text) {
  notice.value = { type, text }
}

async function refresh() {
  await docStore.loadDocuments()
}

async function upload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || !ownerDepartmentId.value) return
  try {
    const shared = sharedDepartments.value.split(',').map(value => value.trim()).filter(Boolean)
    await docStore.upload(file, ownerDepartmentId.value, visibility.value, shared)
    show('success', `${file.name} 已创建为草稿`)
  } catch (error) {
    show('error', error.response?.data?.message || '上传失败')
  }
}

async function submitReview(doc) {
  const reason = window.prompt('提交说明')?.trim()
  if (!reason) return
  await run(doc, () => docStore.submit(doc.document_id, reason), '已提交审核')
}

async function approve(doc) {
  const reason = window.prompt('批准理由')?.trim()
  if (!reason) return
  const password = window.prompt('请输入当前密码完成再认证')
  if (!password) return
  await run(doc, () => docStore.approve(doc.document_id, reason, password), '文档已批准并进入索引')
}

async function revoke(doc) {
  const reason = window.prompt('撤回理由')?.trim()
  if (!reason) return
  const password = window.prompt('请输入当前密码完成再认证')
  if (!password) return
  await run(doc, () => docStore.revoke(doc.document_id, reason, password), '文档已撤回')
}

async function sync(doc) {
  await run(doc, () => docStore.sync(doc.document_id), '索引已重建')
}

async function run(doc, operation, success) {
  try {
    await operation()
    show('success', success)
  } catch (error) {
    show('error', error.response?.data?.message || `${doc.display_name} 操作失败`)
  }
}
</script>

<style scoped>
.documents-view {
  flex: 1;
  max-width: 1280px;
  overflow-y: auto;
  padding: 28px 36px 48px;
}

.upload-band {
  display: flex;
  align-items: end;
  gap: 10px;
  flex-wrap: wrap;
  padding: 14px 0;
  border-top: 1px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
}

.upload-band label:not(.upload-button) {
  display: grid;
  gap: 6px;
}

.upload-band label span {
  color: var(--text-secondary);
  font-size: 12px;
}

.upload-band select,
.upload-band input,
.search-box {
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.shared-input {
  flex: 1;
  min-width: 240px;
}

.upload-button {
  position: relative;
  overflow: hidden;
}

.upload-button input {
  position: absolute;
  inset: 0;
  opacity: 0;
}

.document-metrics {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.search-box {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.search-box input {
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
}

.file-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
}

.file-cell strong,
.file-cell small {
  display: block;
}

.file-cell small {
  margin-top: 2px;
  color: var(--text-tertiary);
}

.row-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.mini-button {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--bg-primary);
  color: var(--text-secondary);
}

.mini-button.success { color: var(--mint); }
.mini-button.danger { color: var(--red); }
.mini-button:disabled { opacity: 0.5; }

code {
  color: var(--text-secondary);
  font-size: 12px;
}

@media (max-width: 760px) {
  .documents-view { padding: 20px 16px 36px; }
  .document-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
