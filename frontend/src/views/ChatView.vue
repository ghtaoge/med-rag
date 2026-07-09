<template>
  <div class="chat-view page-shell">
    <section class="chat-workspace panel">
      <div class="chat-main">
        <div class="chat-content" ref="messagesRef" @scroll="handleMessagesScroll">
        <div class="welcome-strip" v-if="!chatStore.question && !chatStore.answer && !chatStore.isStreaming">
          <div class="welcome-copy">
            <div class="welcome-title-row">
              <span class="welcome-icon"><Stethoscope :size="22" /></span>
              <p class="eyebrow">知识问答</p>
            </div>
            <h2>今天想查点什么？</h2>
            <p>输入医疗相关问题，系统会从已上传文档里找依据，回答后把来源、相关片段和校验结果放在右侧。</p>
          </div>
          <div class="quick-note">
            <ShieldCheck :size="20" />
            <strong>使用前小提醒</strong>
            <span>先确认文档已同步；回答用于知识核对，不替代医生诊断。</span>
          </div>
        </div>

        <div class="prompt-chips" v-if="!chatStore.answer && !chatStore.isStreaming">
          <button
            v-for="item in exampleQuestions"
            :key="item.text"
            type="button"
            class="prompt-chip"
            @click="ask(item.text)"
          >
            <component :is="item.icon" :size="16" />
            <span>{{ item.text }}</span>
          </button>
        </div>

        <div class="messages">
          <article v-if="chatStore.question" class="message-row user">
            <div class="avatar"><UserRound :size="17" /></div>
            <div class="bubble">{{ chatStore.question }}</div>
          </article>

          <div v-if="chatStore.isLlmFallback" class="llm-fallback-notice">
            ⚠️ 知识库中未检索到相关内容，以下为模型基于通用知识的回答，仅供参考
          </div>

          <div v-if="chatStore.intent" class="intent-line">
            <span class="badge" :class="intentClass">
              <SearchCheck :size="14" />
              {{ intentLabel }} · 置信度 {{ chatStore.intent.confidence }} · {{ methodLabel(chatStore.intent.method) }}
            </span>
          </div>

          <article v-if="chatStore.answer" class="message-row assistant">
            <div class="avatar"><Cross :size="17" /></div>
            <div class="bubble answer-bubble">
              <div class="answer-text" v-html="renderedAnswer"></div>
              <div v-if="chatStore.isStreaming" class="streaming-indicator">
                <LoaderCircle :size="16" class="spin" />
                正在继续整理回答
              </div>
            </div>
          </article>

          <div v-if="chatStore.isStreaming && !chatStore.answer" class="empty-stream">
            <LoaderCircle :size="16" class="spin" />
            正在检索相关资料
          </div>
        </div>
        </div>

        <form class="composer" @submit.prevent="handleSubmit">
          <div class="composer-input">
            <Search :size="18" />
            <textarea
              v-model="inputQuestion"
              rows="2"
              placeholder="输入问题，例如：阿司匹林有哪些常见适应症？"
              :disabled="chatStore.isStreaming"
              @keydown.enter.exact.prevent="handleSubmit"
            ></textarea>
          </div>
          <div class="composer-actions">
            <button
              type="button"
              class="btn btn-ghost"
              :disabled="!chatStore.question && !chatStore.answer"
              @click="chatStore.clearChat()"
            >
              <RotateCcw :size="16" />
              清空
            </button>
            <button
              v-if="chatStore.isStreaming"
              type="button"
              class="btn btn-danger"
              @click="chatStore.stopStream()"
            >
              <Square :size="15" />
              停止
            </button>
            <button v-else type="submit" class="btn btn-primary" :disabled="!inputQuestion.trim()">
              <SendHorizontal :size="16" />
              发送
            </button>
          </div>
        </form>
      </div>

      <aside class="insight-panel">
        <section class="side-section">
          <div class="section-heading">
            <span><ShieldCheck :size="17" /> 回答校验</span>
            <span class="badge" :class="confidenceClass">{{ confidenceText }}</span>
          </div>

          <div v-if="chatStore.correctness" class="confidence-card">
            <div class="score-block">
              <strong>{{ scorePercent }}%</strong>
              <span>综合评分</span>
            </div>
            <div class="confidence-meta">
              <p>{{ chatStore.correctness.source_count }} 个来源参与校验</p>
              <small>如发现来源冲突或高风险表述，会在这里提示。</small>
            </div>
          </div>
          <div v-else class="muted-box">
            <CircleHelp :size="16" />
            <span>回答完成后，这里会显示置信度、来源数量和风险提示。</span>
          </div>

          <div v-if="chatStore.correctness?.warnings?.length" class="alert-list">
            <div v-for="w in chatStore.correctness.warnings" :key="w" class="notice warning">{{ w }}</div>
          </div>
          <div v-if="chatStore.correctness?.hallucination_flags?.length" class="alert-list">
            <div v-for="h in chatStore.correctness.hallucination_flags" :key="h" class="notice error">{{ h }}</div>
          </div>
        </section>

        <section class="side-section sources-section">
          <div class="section-heading">
            <span><BookOpenText :size="17" /> 引用来源</span>
            <span class="count">{{ chatStore.sources?.length || 0 }}</span>
          </div>

          <div v-if="chatStore.sources?.length" class="source-list">
            <article v-for="(s, i) in chatStore.sources" :key="i" class="source-card">
              <div class="source-top">
                <span class="badge badge-info"><FileText :size="14" /> {{ s.source || `来源 ${i + 1}` }}</span>
                <small>相关度 {{ s.score }}</small>
              </div>
              <p>{{ s.content_preview }}</p>
            </article>
          </div>
          <div v-else class="muted-box">
            <BookOpenText :size="16" />
            <span>系统找到引用片段后会显示在这里，便于回到原文核对。</span>
          </div>
        </section>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { useChatStore } from '../stores/chat'
import MarkdownIt from 'markdown-it'
import {
  BookOpenText,
  CircleHelp,
  Cross,
  FileText,
  HeartPulse,
  LoaderCircle,
  Pill,
  RotateCcw,
  Search,
  SearchCheck,
  SendHorizontal,
  ShieldCheck,
  Square,
  Stethoscope,
  UserRound,
} from 'lucide-vue-next'

const md = new MarkdownIt({ html: false, breaks: true })
const chatStore = useChatStore()
const inputQuestion = ref('')
const messagesRef = ref(null)
const shouldAutoScroll = ref(true)

const exampleQuestions = [
  { text: '阿司匹林的适应症有哪些？', icon: Pill },
  { text: '布洛芬和对乙酰氨基酚有什么区别？', icon: HeartPulse },
  { text: '药品不良反应如何处理？', icon: ShieldCheck },
]

const intentLabel = computed(() => {
  const map = { query: '查询', definition: '定义', comparison: '对比', process: '流程', negation: '否定' }
  return map[chatStore.intent?.category] || '查询'
})

const intentClass = computed(() => {
  const map = {
    query: 'badge-info',
    definition: 'badge-success',
    comparison: 'badge-warning',
    process: 'badge-info',
    negation: 'badge-danger',
  }
  return map[chatStore.intent?.category] || 'badge-info'
})

const renderedAnswer = computed(() => md.render(chatStore.answer || ''))
const score = computed(() => Math.round((chatStore.correctness?.score || 0) * 100))
const scorePercent = computed(() => Math.max(0, Math.min(100, score.value)))

const confidenceText = computed(() => {
  const c = chatStore.correctness?.confidence
  if (c === 'high') return '较可靠'
  if (c === 'medium') return '需核对'
  if (c === 'low') return '谨慎使用'
  return '待生成'
})

const confidenceClass = computed(() => {
  const c = chatStore.correctness?.confidence
  if (c === 'high') return 'badge-success'
  if (c === 'medium') return 'badge-warning'
  if (c === 'low') return 'badge-danger'
  return 'badge-info'
})

function methodLabel(method) {
  if (!method) return '自动识别'
  return method === 'rule' ? '规则识别' : '模型识别'
}

function ask(question) {
  inputQuestion.value = question
  handleSubmit()
}

function scrollMessagesToBottom(force = false) {
  nextTick(() => {
    const el = messagesRef.value
    if (!el || (!force && !shouldAutoScroll.value)) return
    el.scrollTop = el.scrollHeight
  })
}

function handleMessagesScroll() {
  const el = messagesRef.value
  if (!el) return
  const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  shouldAutoScroll.value = distanceToBottom < 80
}

function handleSubmit() {
  const question = inputQuestion.value.trim()
  if (!question || chatStore.isStreaming) return
  shouldAutoScroll.value = true
  chatStore.startStream(question)
  inputQuestion.value = ''
  scrollMessagesToBottom(true)
}

watch(
  () => [
    chatStore.question,
    chatStore.answer,
    chatStore.intent,
    chatStore.correctness,
    chatStore.isStreaming,
  ],
  () => scrollMessagesToBottom(),
  { flush: 'post' },
)
</script>

<style scoped>
.chat-view {
  flex: 1;
  min-height: 0;
  height: calc(100vh - 54px);
  width: 100%;
}

.chat-workspace {
  height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  overflow: hidden;
  border: 0;
  border-radius: 0;
  background: var(--bg-primary);
}

.chat-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  overflow: hidden;
}

.chat-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scroll-behavior: smooth;
  scrollbar-gutter: stable;
}

.welcome-strip {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 250px;
  gap: 14px;
  margin: 16px 20px 0;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.welcome-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.welcome-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--accent-color-light);
  color: var(--accent-color);
}

.welcome-copy h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
}

.welcome-copy p:last-child {
  max-width: 680px;
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.quick-note {
  align-self: stretch;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 7px;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--accent-color);
}

.quick-note strong {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.quick-note span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.prompt-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 20px 0;
}

.prompt-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.prompt-chip:hover {
  border-color: rgba(99, 102, 241, 0.35);
  background: var(--accent-color-light);
  color: var(--text-primary);
}

.llm-fallback-notice {
  margin: 0 20px 12px;
  padding: 10px 14px;
  border: 1px solid var(--amber);
  border-radius: 8px;
  background: rgba(245, 158, 11, 0.12);
  color: var(--amber);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.6;
}

.messages {
  padding: 16px 20px;
}

.message-row {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.user .avatar {
  order: 2;
  background: var(--accent-color-light);
  color: var(--accent-color);
}

.message-row.user .bubble {
  max-width: min(720px, 82%);
  background: var(--accent-color-light);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: var(--text-primary);
}

.message-row.assistant .avatar {
  background: #1a1b2e;
  color: var(--text-secondary);
}

.avatar {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  border-radius: 10px;
  font-size: 13px;
}

.bubble {
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.7;
  white-space: normal;
  word-break: break-word;
}

.answer-bubble {
  max-width: min(820px, 92%);
}

.answer-text :deep(p) {
  margin: 0 0 10px;
}

.answer-text :deep(p:last-child) {
  margin-bottom: 0;
}

.answer-text :deep(ul),
.answer-text :deep(ol) {
  padding-left: 22px;
}

.intent-line {
  margin: -2px 0 12px 46px;
}

.streaming-indicator,
.empty-stream {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.empty-stream {
  padding: 10px 14px;
  border-radius: 8px;
  color: var(--text-secondary);
}

.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.composer {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  padding: 12px 24px 16px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-primary);
}

.composer-input {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-tertiary);
}

.composer textarea {
  width: 100%;
  min-height: 42px;
  max-height: 120px;
  resize: none;
  padding: 0;
  border: 0;
  outline: none;
  color: var(--text-primary);
  background: transparent;
  line-height: 1.5;
}

.composer textarea::placeholder {
  color: var(--text-tertiary);
}

.composer-input:focus-within {
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.16);
}

.composer-actions {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.insight-panel {
  min-width: 0;
  padding: 8px;
  border-left: 1px solid var(--border-color);
  background: var(--bg-secondary);
  overflow-y: auto;
}

.side-section {
  padding: 10px;
  margin-bottom: 8px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
}

.section-heading span:first-child {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.count {
  color: var(--text-tertiary);
  font-size: 12px;
}

.confidence-card {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.score-block {
  display: grid;
  place-items: center;
  width: 78px;
  height: 64px;
  flex: 0 0 78px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-tertiary);
}

.score-block strong,
.score-block span {
  display: block;
}

.score-block strong {
  align-self: end;
  color: var(--text-primary);
  font-size: 20px;
  font-weight: 650;
}

.score-block span {
  align-self: start;
  color: var(--text-tertiary);
  font-size: 11px;
}

.confidence-meta p {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-weight: 500;
}

.confidence-meta small,
.muted-box {
  color: var(--text-secondary);
  line-height: 1.55;
}

.muted-box {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  font-size: 13px;
}

.alert-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.source-list {
  display: grid;
  gap: 8px;
}

.source-card {
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.source-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}

.source-top small {
  color: var(--text-tertiary);
  font-size: 12px;
}

.source-card p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 1100px) {
  .chat-workspace {
    grid-template-columns: 1fr;
  }

  .insight-panel {
    border-left: 0;
    border-top: 1px solid var(--border-color);
  }

  .chat-view {
    height: auto;
  }
}

@media (max-width: 720px) {
  .welcome-strip,
  .composer {
    grid-template-columns: 1fr;
  }

  .composer {
    display: flex;
    flex-direction: column;
    padding: 12px 16px 16px;
  }

  .composer-actions {
    justify-content: flex-end;
  }
}
</style>
