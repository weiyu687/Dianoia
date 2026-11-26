<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Activity, ArrowDown, ArrowUp, ArrowUpRight, BookOpen, BookOpenCheck, Check, ChevronDown,
  ClipboardList, Copy, Ellipsis, FileText, Film, LoaderCircle, MessageSquare, PanelLeft,
  Pencil, Presentation, Search, Sparkles, Square, SquarePen, Trash2, Workflow, X,
} from 'lucide-vue-next'
import { api } from '../api'
import MarkdownContent from '../components/MarkdownContent.vue'
import { course, courseId } from '../session'

const conversations = ref([])
const current = ref(null)
const input = ref('')
const queue = ref([])
const mode = ref('queue')
const sending = ref(false)
const loadingHistory = ref(true)
const loadingConversation = ref(false)
const error = ref('')
const notice = ref('')
const scrollArea = ref(null)
const composerInput = ref(null)
const historyOpen = ref(!window.matchMedia('(max-width: 900px)').matches)
const historyQuery = ref('')
const menuId = ref(null)
const renameId = ref(null)
const renameTitle = ref('')
const atBottom = ref(true)
const copiedId = ref(null)
const stopping = ref(false)
let pollTimer = null
let requestVersion = 0
let disposed = false
let draining = false
let guiding = false
let copyTimer

const messages = computed(() => current.value?.messages ?? [])
const busy = computed(() => sending.value || !!current.value?.busy ||
  messages.value.some((message) => ['thinking', 'stopping'].includes(message.status)))
const filteredHistory = computed(() => {
  const query = historyQuery.value.trim().toLocaleLowerCase()
  return conversations.value.filter((row) => row.title.toLocaleLowerCase().includes(query))
})
const artifactIcons = {
  lesson: BookOpen, mind_map: Workflow, exam: ClipboardList, presentation: Presentation,
  question_bank: BookOpenCheck, learning_plan: Activity, digital_course: Film,
}
const legacyGroups = {
  created_lessons: ['lesson', '教案草稿', '/lessons/'],
  created_mind_maps: ['mind_map', '思维导图', '/mind-maps/'],
  created_exams: ['exam', '试卷草稿', '/exams/'],
  created_presentations: ['presentation', '演示文稿', '/presentations/'],
  question_banks: ['question_bank', '在线题库', '/question-banks/'],
}

function messageArtifacts(result) {
  if (!result) return []
  if (Array.isArray(result.artifacts)) {
    return result.artifacts.filter(({ route }) => typeof route === 'string' && /^\/[a-z]/.test(route))
  }
  const cards = Object.entries(legacyGroups).flatMap(([key, [kind, label, base]]) =>
    (result[key] || []).map((row) => ({ ...row, kind, label, route: base + encodeURIComponent(row.id) })))
  for (const row of result.presentation_suggestions || []) {
    cards.push({ ...row, kind: 'presentation', label: `第 ${row.page} 页修改候选`,
      route: { name: 'presentation', params: { id: row.presentation_id }, query: { page: row.page, candidate: row.id } } })
  }
  return cards
}

function summary(row) {
  return {
    id: row.id,
    course_id: row.course_id,
    title: row.title,
    created_at: row.created_at,
    updated_at: row.updated_at,
    busy: row.busy,
  }
}

function remember(row) {
  const item = summary(row)
  conversations.value = [item, ...conversations.value.filter((entry) => entry.id !== item.id)]
    .sort((left, right) => String(right.updated_at).localeCompare(String(left.updated_at)))
}

async function loadHistory() {
  loadingHistory.value = true
  error.value = ''
  try {
    const rows = await api(`/agent/conversations?course_id=${courseId.value}`)
    if (disposed) return
    conversations.value = rows
    if (!current.value && conversations.value.length) {
      await openConversation(conversations.value[0].id)
    }
  } catch (failure) {
    error.value = failure.message
  } finally {
    loadingHistory.value = false
    if (current.value) await scrollToLatest()
  }
}

async function openConversation(id) {
  if (busy.value) return
  const version = ++requestVersion
  loadingConversation.value = true
  error.value = ''
  notice.value = ''
  menuId.value = null
  try {
    const row = await api(`/agent/conversations/${id}`)
    if (disposed || version !== requestVersion) return
    current.value = row
    if (window.matchMedia('(max-width: 900px)').matches) historyOpen.value = false
    remember(current.value)
    schedulePoll()
  } catch (failure) {
    if (version === requestVersion) error.value = failure.message
  } finally {
    if (version === requestVersion) {
      loadingConversation.value = false
      await scrollToLatest()
    }
  }
}

function newConversation() {
  if (busy.value) return
  requestVersion += 1
  current.value = null
  loadingConversation.value = false
  input.value = ''
  queue.value = []
  error.value = ''
  notice.value = ''
  clearTimeout(pollTimer)
  menuId.value = null
  if (window.matchMedia('(max-width: 900px)').matches) historyOpen.value = false
  nextTick(() => composerInput.value?.focus())
}

async function refreshCurrent(silent = false) {
  if (!current.value?.id) return
  const id = current.value.id
  const version = requestVersion
  try {
    const row = await api(`/agent/conversations/${id}`)
    if (disposed || version !== requestVersion || current.value?.id !== id) return
    current.value = row
    remember(row)
    if (!silent && !busy.value) notice.value = ''
    schedulePoll()
    if (atBottom.value) await scrollToLatest()
  } catch (failure) {
    if (disposed || version !== requestVersion) return
    if (!silent) error.value = failure.message
    schedulePoll()
  }
}

function schedulePoll() {
  clearTimeout(pollTimer)
  if (disposed || !busy.value || sending.value || stopping.value) return
  pollTimer = setTimeout(() => refreshCurrent(true), 900)
}

async function scrollToLatest(behavior = 'instant') {
  await nextTick()
  const area = scrollArea.value
  if (area) area.scrollTo({ top: area.scrollHeight, behavior })
  atBottom.value = true
}

function trackScroll() {
  const area = scrollArea.value
  atBottom.value = !area || area.scrollHeight - area.clientHeight - area.scrollTop < 90
}

async function ensureConversation() {
  if (current.value?.id) return current.value.id
  const row = await api('/agent/conversations', {
    method: 'POST',
    body: { course_id: courseId.value },
  })
  current.value = { ...row, messages: [] }
  remember(row)
  return row.id
}

async function sendNow(text) {
  if (disposed || !text.trim() || sending.value) return
  requestVersion += 1
  sending.value = true
  error.value = ''
  notice.value = ''
  try {
    const id = await ensureConversation()
    const stamp = Date.now()
    current.value = {
      ...current.value,
      busy: true,
      messages: [
        ...(current.value?.messages ?? []),
        { id: `user-${stamp}`, role: 'user', content: text, status: 'complete', result: {} },
        { id: `assistant-${stamp}`, role: 'assistant', content: '', status: 'thinking', result: {} },
      ],
    }
    await scrollToLatest()
    const row = await api(`/agent/conversations/${id}/messages`, {
      method: 'POST',
      body: { content: text },
    })
    current.value = row
    remember(row)
    return true
  } catch (failure) {
    error.value = failure.message
    if (!input.value) input.value = text
    await refreshCurrent(true)
    return false
  } finally {
    sending.value = false
    schedulePoll()
  }
}

async function submit() {
  const text = input.value.trim()
  if (!text || stopping.value || loadingConversation.value || loadingHistory.value) return
  input.value = ''
  if (busy.value) {
    if (!sending.value && mode.value === 'guide') {
      await guide(text)
    } else {
      queue.value.push({ id: `${Date.now()}-${queue.value.length}`, content: text })
      notice.value = '已加入发送队列，将在当前回复结束后自动发送。'
    }
    return
  }
  await sendNow(text)
}

async function guide(text) {
  guiding = true
  notice.value = '正在停止当前回复并处理新的引导…'
  try {
    await cancelCurrent(false, true)
    if (await sendNow(text)) notice.value = '已按引导开始新的回复。'
  } catch (failure) {
    error.value = failure.message
    if (!input.value) input.value = text
  } finally {
    guiding = false
  }
}

async function cancelCurrent(clearQueue = true, rethrow = false) {
  if (!current.value?.id || sending.value || stopping.value) return
  requestVersion += 1
  stopping.value = true
  clearTimeout(pollTimer)
  try {
    current.value = await api(`/agent/conversations/${current.value.id}/cancel`, { method: 'POST' })
    if (clearQueue) queue.value = []
    remember(current.value)
    notice.value = '已停止当前回复。'
  } catch (failure) {
    error.value = failure.message
    if (rethrow) throw failure
  } finally {
    stopping.value = false
    schedulePoll()
  }
}

function removeQueued(id) {
  queue.value = queue.value.filter((item) => item.id !== id)
}

async function removeConversation(row) {
  if (busy.value || !window.confirm(`删除对话「${row.title}」？此操作不可恢复。`)) return
  try {
    menuId.value = null
    await api(`/agent/conversations/${row.id}`, { method: 'DELETE' })
    conversations.value = conversations.value.filter((item) => item.id !== row.id)
    if (current.value?.id === row.id) newConversation()
  } catch (failure) {
    error.value = failure.message
  }
}

async function beginRename(row) {
  menuId.value = null
  renameId.value = row.id
  renameTitle.value = row.title
  await nextTick()
  document.getElementById('agent-rename-title')?.select()
}

async function renameConversation() {
  const id = renameId.value
  const title = renameTitle.value.trim()
  if (!id || !title) return
  try {
    const row = await api(`/agent/conversations/${id}`, { method: 'PATCH', body: { title } })
    remember(row)
    if (current.value?.id === id) current.value = { ...current.value, title: row.title, updated_at: row.updated_at }
    renameId.value = null
  } catch (failure) {
    error.value = failure.message
  }
}

function handleComposerKeydown(event) {
  if (event.key !== 'Enter' || event.isComposing || event.keyCode === 229) return
  if (event.shiftKey && !event.ctrlKey) return
  event.preventDefault()
  submit()
}

async function copyMessage(message) {
  try {
    await navigator.clipboard.writeText(message.content)
    copiedId.value = message.id
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copiedId.value = null }, 1500)
  } catch {
    error.value = '复制失败，请手动选择文字。'
  }
}

watch(busy, async (active) => {
  if (active) {
    schedulePoll()
    return
  }
  clearTimeout(pollTimer)
  if (disposed || draining || guiding || !queue.value.length || sending.value || stopping.value) return
  draining = true
  try {
    const next = queue.value.shift()
    notice.value = '正在发送排队中的问题…'
    await sendNow(next.content)
  } finally {
    draining = false
  }
})

watch(input, async () => {
  await nextTick()
  const field = composerInput.value
  if (!field) return
  field.style.height = 'auto'
  field.style.height = `${field.scrollHeight}px`
})

onMounted(async () => {
  await loadHistory()
  schedulePoll()
})

onBeforeUnmount(() => {
  disposed = true
  clearTimeout(pollTimer)
  clearTimeout(copyTimer)
})
</script>

<template>
  <div class="chat-workspace" @keydown.esc="menuId = null; renameId = null">
    <button v-if="historyOpen" class="chat-backdrop" type="button" aria-label="关闭对话历史" @click="historyOpen = false"></button>
    <aside v-if="historyOpen" class="chat-history" aria-label="对话历史">
      <div class="chat-history-heading">
        <strong>对话历史</strong>
        <button class="chat-icon-button" type="button" aria-label="收起对话历史" title="收起对话历史" @click="historyOpen = false">
          <PanelLeft :size="18" />
        </button>
      </div>
      <button class="chat-new" type="button" :disabled="busy" @click="newConversation">
        <SquarePen :size="17" /> 新建对话
      </button>
      <label class="chat-search">
        <Search :size="16" aria-hidden="true" />
        <input v-model="historyQuery" type="search" aria-label="搜索对话" placeholder="搜索对话">
      </label>
      <div class="chat-history-list">
        <p v-if="loadingHistory" class="chat-list-state" role="status">正在加载对话</p>
        <p v-else-if="!filteredHistory.length" class="chat-list-state">{{ historyQuery ? '没有匹配的对话' : '暂无历史对话' }}</p>
        <article v-for="row in filteredHistory" :key="row.id" class="chat-history-row"
          :class="{ 'is-current': current?.id === row.id, 'menu-open': menuId === row.id }">
          <form v-if="renameId === row.id" class="chat-rename" @submit.prevent="renameConversation">
            <input id="agent-rename-title" v-model="renameTitle" maxlength="120" aria-label="对话名称">
            <button class="chat-icon-button" type="submit" aria-label="保存名称" :disabled="!renameTitle.trim()"><Check :size="16" /></button>
            <button class="chat-icon-button" type="button" aria-label="取消重命名" @click="renameId = null"><X :size="16" /></button>
          </form>
          <template v-else>
            <button class="chat-history-open" type="button" :disabled="busy && current?.id !== row.id"
              :aria-current="current?.id === row.id ? 'true' : undefined" :title="row.title" @click="openConversation(row.id)">
              <MessageSquare :size="15" /><span>{{ row.title }}</span>
              <LoaderCircle v-if="row.busy" class="chat-spin" :size="13" aria-label="正在回复" />
            </button>
            <button class="chat-icon-button chat-more" type="button" :disabled="busy" :aria-label="'管理对话 ' + row.title"
              :aria-expanded="menuId === row.id" @click="menuId = menuId === row.id ? null : row.id"><Ellipsis :size="17" /></button>
            <div v-if="menuId === row.id" class="chat-history-menu">
              <button type="button" @click="beginRename(row)"><Pencil :size="14" />重命名</button>
              <button class="chat-delete" type="button" @click="removeConversation(row)"><Trash2 :size="14" />删除</button>
            </div>
          </template>
        </article>
      </div>
    </aside>

    <section class="chat-main" aria-label="教师 Agent">
      <header class="chat-top">
        <button v-if="!historyOpen" class="chat-icon-button" type="button" aria-label="打开对话历史" title="打开对话历史" @click="historyOpen = true">
          <PanelLeft :size="19" />
        </button>
        <div class="chat-title">
          <h1>{{ current?.title || '教师 Agent' }}</h1>
          <span>{{ course?.name }}</span>
        </div>
        <button v-if="!historyOpen" class="chat-icon-button chat-new-compact" type="button" aria-label="新建对话"
          title="新建对话" :disabled="busy" @click="newConversation"><SquarePen :size="19" /></button>
      </header>

      <div ref="scrollArea" class="chat-scroll" @scroll.passive="trackScroll">
        <div v-if="loadingConversation || loadingHistory" class="chat-welcome" role="status">
          <LoaderCircle class="chat-spin" :size="23" /> 正在加载对话
        </div>
        <div v-else-if="!messages.length" class="chat-welcome">
          <span class="chat-orb"><Sparkles :size="26" :stroke-width="1.7" /></span>
          <h2>今天想处理什么？</h2>
        </div>
        <div v-else class="chat-transcript" role="log" aria-label="对话消息" aria-live="polite">
          <article v-for="message in messages" :key="message.id" class="chat-message" :class="message.role">
            <template v-if="message.role === 'user'">
              <span class="sr-only">你</span>
              <p class="chat-user-bubble">{{ message.content }}</p>
            </template>
            <template v-else>
              <div class="chat-assistant-label"><span class="chat-assistant-icon"><Sparkles :size="16" /></span><strong>Dianoia</strong></div>
              <div class="chat-reply">
                <div v-if="['thinking', 'stopping'].includes(message.status)" class="chat-thinking" role="status">
                  <span class="chat-thinking-dot"></span>{{ message.status === 'stopping' || stopping ? '正在停止' : '正在处理' }}
                </div>
                <p v-else-if="message.status === 'failed'" class="chat-failure">{{ message.result?.user_error || message.content || '这次回复未能完成，请稍后重试。' }}</p>
                <MarkdownContent v-else-if="message.content" :text="message.content" />
                <p v-else-if="message.status === 'cancelled'" class="muted">已停止生成</p>
                <p v-else-if="message.status === 'interrupted'" class="muted">服务重启时回复中断，请重新发送。</p>
                <div v-if="messageArtifacts(message.result).length" class="chat-artifacts">
                  <RouterLink v-for="card in messageArtifacts(message.result)" :key="card.label + ':' + card.id"
                    :to="card.route" class="chat-artifact">
                    <span class="chat-artifact-icon"><component :is="artifactIcons[card.kind] || FileText" :size="19" /></span>
                    <span><small>{{ card.label }}</small><strong>{{ card.title }}</strong></span>
                    <ArrowUpRight :size="17" />
                  </RouterLink>
                </div>
                <div v-if="message.status === 'complete' && message.content" class="chat-message-actions">
                  <button class="chat-icon-button" type="button" :title="copiedId === message.id ? '已复制' : '复制回复'"
                    :aria-label="copiedId === message.id ? '已复制' : '复制回复'" @click="copyMessage(message)">
                    <Check v-if="copiedId === message.id" :size="16" /><Copy v-else :size="16" />
                  </button>
                </div>
              </div>
            </template>
          </article>
        </div>
      </div>

      <footer class="chat-composer-zone">
        <div class="chat-composer-inner">
          <button v-if="!atBottom && messages.length" class="chat-icon-button chat-jump" type="button" aria-label="跳到最新消息"
            title="跳到最新消息" @click="scrollToLatest('smooth')"><ArrowDown :size="18" /></button>
          <p v-if="error" class="chat-failure chat-notice" role="alert">{{ error }}</p>
          <p v-else-if="notice" class="chat-notice" role="status">{{ notice }}</p>
          <div v-if="queue.length" class="chat-queue" aria-label="待发送消息">
            <div v-for="item in queue" :key="item.id">
              <span>{{ item.content }}</span>
              <button class="chat-icon-button" type="button" :aria-label="'取消排队 ' + item.content" @click="removeQueued(item.id)"><X :size="14" /></button>
            </div>
          </div>
          <form class="chat-composer" @submit.prevent="submit">
            <textarea ref="composerInput" v-model="input" aria-label="对话内容" placeholder="给教师 Agent 发消息…"
              rows="1" maxlength="16000" @keydown="handleComposerKeydown"></textarea>
            <div class="chat-composer-bar">
              <label v-if="busy" class="chat-mode"><span class="sr-only">回复期间的新消息方式</span>
                <select v-model="mode" :disabled="stopping">
                  <option value="queue">排队发送</option>
                  <option value="guide">停止并引导</option>
                </select><ChevronDown :size="13" aria-hidden="true" />
              </label>
              <span v-else class="chat-keyboard-hint">Shift + Enter 换行</span>
              <div class="chat-composer-actions">
                <button v-if="busy" class="chat-icon-button chat-stop" type="button" aria-label="停止回复"
                  title="停止回复" :disabled="sending || stopping" @click="cancelCurrent()"><Square :size="15" /></button>
                <button class="chat-send" type="submit" aria-label="发送消息" title="发送消息"
                  :disabled="!input.trim() || stopping || loadingConversation || loadingHistory"><ArrowUp :size="20" :stroke-width="2.4" /></button>
              </div>
            </div>
          </form>
        </div>
      </footer>
    </section>
  </div>
</template>

<style scoped src="./agent-chat.css"></style>
