<template>
  <div class="chat-view">
    <!-- 左侧：对话区 -->
    <div class="chat-main">
      <!-- 消息列表 -->
      <div class="chat-messages" ref="messagesRef">
        <!-- 欢迎信息 -->
        <div v-if="!chatStore.answer && !chatStore.isStreaming" class="welcome-message">
          <el-icon :size="64" color="#409EFF"><FirstAidKit /></el-icon>
          <h2>Med-Rag 医疗知识助手</h2>
          <p>基于知识库的智能问答，回答标注来源，自动检测幻觉</p>
          <div class="example-questions">
            <el-tag
              v-for="q in exampleQuestions"
              :key="q"
              @click="chatStore.startStream(q)"
              class="example-tag"
              effect="plain"
              size="large"
            >
              {{ q }}
            </el-tag>
          </div>
        </div>

        <!-- 用户问题 -->
        <div v-if="chatStore.question" class="message user-message">
          <div class="message-avatar user-avatar">
            <el-icon><User /></el-icon>
          </div>
          <div class="message-content">{{ chatStore.question }}</div>
        </div>

        <!-- 意图识别 -->
        <div v-if="chatStore.intent" class="intent-badge">
          <el-tag :type="intentType" size="small">
            意图: {{ intentLabel }} ({{ chatStore.intent.confidence }}) — {{ chatStore.intent.method }}模式
          </el-tag>
        </div>

        <!-- AI 回答 -->
        <div v-if="chatStore.answer" class="message ai-message">
          <div class="message-avatar ai-avatar">
            <el-icon><FirstAidKit /></el-icon>
          </div>
          <div class="message-content">
            <div class="answer-text" v-html="renderedAnswer"></div>
            <div v-if="chatStore.isStreaming" class="streaming-indicator">
              <el-icon class="is-loading"><Loading /></el-icon> 正在生成...
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-input">
        <el-input
          v-model="inputQuestion"
          placeholder="输入您的医疗相关问题..."
          :disabled="chatStore.isStreaming"
          @keydown.enter="handleSubmit"
          size="large"
          class="chat-input-field"
        >
          <template #append>
            <el-button
              :icon="chatStore.isStreaming ? 'VideoPause' : 'Promotion'"
              :type="chatStore.isStreaming ? 'danger' : 'primary'"
              @click="chatStore.isStreaming ? chatStore.stopStream() : handleSubmit()"
            />
          </template>
        </el-input>
      </div>
    </div>

    <!-- 右侧：来源 + 置信度 -->
    <div class="chat-sidebar" v-if="chatStore.answer">
      <!-- 正确性校验 -->
      <div v-if="chatStore.correctness" class="sidebar-section">
        <h4>正确性校验</h4>
        <div class="confidence-card">
          <div class="confidence-score">
            <el-progress
              :percentage="chatStore.correctness.score * 100"
              :color="confidenceColor"
              :stroke-width="8"
            />
          </div>
          <div class="confidence-label">
            <el-tag :type="confidenceTagType" size="large">
              {{ chatStore.correctness.confidence }} 置信度
            </el-tag>
            <el-text size="small" type="info">
              {{ chatStore.correctness.source_count }} 个独立来源
            </el-text>
          </div>
        </div>
        <!-- 警告 -->
        <div v-if="chatStore.correctness.warnings?.length" class="warnings">
          <el-alert
            v-for="w in chatStore.correctness.warnings"
            :key="w"
            :title="w"
            type="warning"
            :closable="false"
            show-icon
          />
        </div>
        <!-- 幻觉标记 -->
        <div v-if="chatStore.correctness.hallucination_flags?.length" class="hallucination">
          <el-alert
            v-for="h in chatStore.correctness.hallucination_flags"
            :key="h"
            :title="h"
            type="error"
            :closable="false"
            show-icon
          />
        </div>
      </div>

      <!-- 来源列表 -->
      <div v-if="chatStore.sources?.length" class="sidebar-section">
        <h4>知识来源</h4>
        <el-card
          v-for="(s, i) in chatStore.sources"
          :key="i"
          shadow="hover"
          class="source-card"
        >
          <template #header>
            <div class="source-header">
              <el-tag size="small" type="info">{{ s.source }}</el-tag>
              <el-text size="small">相关度: {{ s.score }}</el-text>
            </div>
          </template>
          <el-text size="small">{{ s.content_preview }}</el-text>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useChatStore } from '../stores/chat'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false })

const chatStore = useChatStore()
const inputQuestion = ref('')
const messagesRef = ref(null)

const exampleQuestions = [
  '阿司匹林的适应症有哪些？',
  '布洛芬和对乙酰氨基酚有什么区别？',
  '药品不良反应如何处理？',
]

const intentLabel = computed(() => {
  const map = { query: '查询', definition: '定义', comparison: '对比', process: '流程', negation: '否定' }
  return map[chatStore.intent?.category] || '查询'
})

const intentType = computed(() => {
  const map = { query: '', definition: 'success', comparison: 'warning', process: 'info', negation: 'danger' }
  return map[chatStore.intent?.category] || ''
})

const renderedAnswer = computed(() => {
  return md.render(chatStore.answer || '')
})

const confidenceColor = computed(() => {
  const s = chatStore.correctness?.score || 0
  if (s >= 0.8) return '#67C23A'
  if (s >= 0.6) return '#E6A23C'
  return '#F56C6C'
})

const confidenceTagType = computed(() => {
  const c = chatStore.correctness?.confidence
  if (c === 'high') return 'success'
  if (c === 'medium') return 'warning'
  return 'danger'
})

function handleSubmit() {
  if (!inputQuestion.value.trim()) return
  chatStore.startStream(inputQuestion.value.trim())
  inputQuestion.value = ''
}
</script>

<style scoped>
.chat-view {
  display: flex;
  height: calc(100vh - 40px);
  gap: 16px;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.welcome-message {
  text-align: center;
  padding: 60px 20px;
}

.welcome-message h2 {
  margin: 16px 0 8px;
  color: #303133;
}

.welcome-message p {
  color: #909399;
  margin-bottom: 24px;
}

.example-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.example-tag {
  cursor: pointer;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-avatar {
  background: #409EFF;
  color: #fff;
}

.ai-avatar {
  background: #67C23A;
  color: #fff;
}

.user-message .message-content {
  background: #ecf5ff;
  padding: 12px 16px;
  border-radius: 8px;
  color: #303133;
}

.ai-message .message-content {
  background: #f4f4f5;
  padding: 12px 16px;
  border-radius: 8px;
  max-width: 100%;
}

.answer-text {
  line-height: 1.6;
}

.answer-text p {
  margin-bottom: 8px;
}

.streaming-indicator {
  color: #409EFF;
  margin-top: 8px;
}

.intent-badge {
  margin-bottom: 12px;
}

.chat-input {
  padding: 16px;
  border-top: 1px solid #e4e7ed;
}

.chat-input-field {
  width: 100%;
}

.chat-sidebar {
  width: 320px;
  background: #fff;
  border-radius: 8px;
  overflow-y: auto;
  padding: 16px;
}

.sidebar-section {
  margin-bottom: 16px;
}

.sidebar-section h4 {
  margin-bottom: 8px;
  color: #303133;
}

.confidence-card {
  padding: 8px;
  background: #f9f9fb;
  border-radius: 6px;
}

.confidence-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.source-card {
  margin-bottom: 8px;
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
