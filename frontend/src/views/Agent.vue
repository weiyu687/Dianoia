<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowUp, History, MessageCircle, Plus, Square, Trash2 } from 'lucide-vue-next'
import { api, formatDate } from '../api'
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
const scrollTarget = ref(null)
let pollTimer = null
let draining = false
let pendingCourseReload = false

const messages = computed(() => current.value?.messages ?? [])
const busy = computed(() => sending.value || messages.value.some((message) => ['thinking', 'stopping'].includes(message.status)))

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

async function loadHistory(openLatest = true) {
  loadingHistory.value = true
  error.value = ''
  try {
    conversations.value = await api(`/agent/conversations?course_id=${courseId.value}`)
    if (!current.value && openLatest && conversations.value.length) {
      await openConversation(conversations.value[0].id)
    }
  } catch (failure) {
    error.value = failure.message
  } finally {
    loadingHistory.value = false
  }
}

async function openConversation(id) {
  if (busy.value) return
  loadingConversation.value = true
  error.value = ''
  try {
    current.value = await api(`/agent/conversations/${id}`)
    remember(current.value)
    await scrollToLatest()
    schedulePoll()
  } catch (failure) {
    error.value = failure.message
  } finally {
    loadingConversation.value = false
  }
}

function newConversation() {
  if (busy.value) return
  current.value = null
  input.value = ''
  queue.value = []
  error.value = ''
  notice.value = ''
  clearTimeout(pollTimer)
}

async function refreshCurrent(silent = false) {
  if (!current.value?.id) return
  try {
    const row = await api(`/agent/conversations/${current.value.id}`)
    current.value = row
    remember(row)
    if (!silent && !busy.value) notice.value = ''
    schedulePoll()
    if (!busy.value) await scrollToLatest()
  } catch (failure) {
    if (!silent) error.value = failure.message
    schedulePoll()
  }
}

function schedulePoll() {
  clearTimeout(pollTimer)
  if (!busy.value) return
  pollTimer = setTimeout(() => refreshCurrent(true), 900)
}

async function scrollToLatest() {
  await nextTick()
  scrollTarget.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
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
  if (!text.trim() || sending.value) return
  sending.value = true
  error.value = ''
  notice.value = ''
  input.value = ''
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
    schedulePoll()
  } catch (failure) {
    error.value = failure.message
    await refreshCurrent(true)
  } finally {
    sending.value = false
    schedulePoll()
  }
}

async function submit() {
  const text = input.value.trim()
  if (!text) return
  input.value = ''
  if (busy.value) {
    if (mode.value === 'guide') {
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
  notice.value = '正在停止当前回复并处理新的引导…'
  try {
    await cancelCurrent(false, true)
    await sendNow(text)
    notice.value = '已按引导开始新的回复。'
  } catch (failure) {
    error.value = failure.message
  }
}

async function cancelCurrent(clearQueue = true, rethrow = false) {
  if (!current.value?.id) {
    sending.value = false
    return
  }
  try {
    current.value = await api(`/agent/conversations/${current.value.id}/cancel`, { method: 'POST' })
    remember(current.value)
    if (clearQueue) queue.value = []
    notice.value = '已停止当前回复。'
    schedulePoll()
  } catch (failure) {
    error.value = failure.message
    if (rethrow) throw failure
  }
}

function removeQueued(id) {
  queue.value = queue.value.filter((item) => item.id !== id)
}

async function removeConversation(row) {
  if (busy.value || !window.confirm(`删除对话「${row.title}」？此操作不可恢复。`)) return
  try {
    await api(`/agent/conversations/${row.id}`, { method: 'DELETE' })
    conversations.value = conversations.value.filter((item) => item.id !== row.id)
    if (current.value?.id === row.id) newConversation()
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
    await navigator.clipboard.writeText(message)
    notice.value = '回复已复制。'
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
  if (pendingCourseReload) {
    pendingCourseReload = false
    current.value = null
    queue.value = []
    input.value = ''
    await loadHistory()
    return
  }
  if (draining || !queue.value.length || sending.value) return
  draining = true
  try {
    const next = queue.value.shift()
    notice.value = '正在发送排队中的问题…'
    await sendNow(next.content)
  } finally {
    draining = false
  }
})

watch(courseId, async () => {
  if (busy.value) {
    pendingCourseReload = true
    return
  }
  current.value = null
  queue.value = []
  input.value = ''
  await loadHistory()
})

onMounted(async () => {
  await loadHistory()
  schedulePoll()
})

onBeforeUnmount(() => clearTimeout(pollTimer))
</script>

<template>
  <div class="page agent-page">
    <div class="agent-layout">
      <aside class="agent-history" aria-label="对话历史">
        <header>
          <div><History :size="17" /><strong>历史对话</strong></div>
          <button class="button primary icon-only" aria-label="新建对话" :disabled="busy" @click="newConversation">
            <Plus :size="18" />
          </button>
        </header>
        <p v-if="loadingHistory" class="muted" role="status">正在加载对话</p>
        <p v-else-if="!conversations.length" class="agent-history-empty">还没有历史对话</p>
        <div v-else class="agent-history-list">
          <article v-for="row in conversations" :key="row.id" :class="{ active: current?.id === row.id }">
            <button class="agent-history-open" :disabled="busy" @click="openConversation(row.id)">
              <strong>{{ row.title }}</strong>
              <small>{{ formatDate(row.updated_at) }}<span v-if="row.busy"> · 正在回复</span></small>
            </button>
            <button class="agent-history-delete" :aria-label="'删除对话 ' + row.title" :disabled="busy" @click="removeConversation(row)">
              <Trash2 :size="14" />
            </button>
          </article>
        </div>
      </aside>

      <section class="agent-main" aria-label="教师 Agent">
        <header class="agent-heading">
          <div>
            <h1>{{ current?.title || '教师 Agent' }}</h1>
            <p>{{ course.name }}<span v-if="current"> · {{ messages.filter((message) => message.role === 'user').length }} 轮对话</span></p>
          </div>
        </header>

        <p v-if="error" class="error agent-alert" role="alert">{{ error }}</p>
        <p v-if="notice" class="agent-notice" role="status">{{ notice }}</p>

        <div class="agent-conversation-wrap">
          <div v-if="loadingConversation" class="agent-empty" role="status">正在打开对话</div>
          <div v-else-if="!messages.length" class="agent-empty">
            <span class="agent-icon"><MessageCircle :size="28" /></span>
            <h2>今天想处理什么？</h2>
            <p>我会基于当前课程的资料完成查询、导图、试卷、题库和课件工作。</p>
          </div>

          <div v-else class="conversation agent-conversation" aria-live="polite">
            <article v-for="message in messages" :key="message.id" class="agent-message" :class="message.role">
              <template v-if="message.role === 'user'">
                <p>{{ message.content }}</p>
              </template>
              <template v-else>
                <div class="agent-message-label"><span>Dianoia</span><small>教师 Agent</small></div>
                <div v-if="message.status === 'thinking'" class="agent-thinking" role="status">
                  <span></span><span></span><span></span><em>正在思考</em>
                </div>
                <MarkdownContent v-else-if="message.content" :text="message.content" />
                <p v-else-if="message.status === 'cancelled'" class="muted">已停止生成。</p>
                <p v-else-if="message.status === 'interrupted'" class="muted">服务重启时这次回复被中断，请重新发送。</p>
                <p v-else-if="message.status === 'failed'" class="error">这次回复未能完成，请稍后重试。</p>
                <div v-if="message.content" class="agent-message-actions">
                  <button @click="copyMessage(message.content)">复制</button>
                </div>
                <RouterLink v-for="deck in message.result?.created_presentations || []" :key="deck.id" class="text-link"
                  :to="'/presentations/' + deck.id">打开课件「{{ deck.title }}」</RouterLink>
                <RouterLink v-for="candidate in message.result?.presentation_suggestions || []" :key="candidate.id" class="text-link"
                  :to="{ name: 'presentation', params: { id: candidate.presentation_id }, query: { page: candidate.page, candidate: candidate.id } }">
                  查看「{{ candidate.title }}」第 {{ candidate.page }} 页候选
                </RouterLink>
                <RouterLink v-for="map in message.result?.created_mind_maps || []" :key="map.id" class="text-link"
                  :to="'/mind-maps/' + map.id">打开导图「{{ map.title }}」</RouterLink>
                <RouterLink v-for="exam in message.result?.created_exams || []" :key="exam.id" class="text-link"
                  :to="'/exams/' + exam.id">打开试卷「{{ exam.title }}」</RouterLink>
                <RouterLink v-for="bank in message.result?.question_banks || []" :key="bank.id" class="text-link"
                  :to="'/question-banks/' + bank.id">打开题库「{{ bank.title }}」</RouterLink>
              </template>
            </article>
          </div>
          <span ref="scrollTarget"></span>
        </div>

        <div class="agent-composer-shell">
          <div v-if="queue.length" class="agent-queue" aria-label="待发送消息">
            <div v-for="item in queue" :key="item.id">
              <span>{{ item.content }}</span>
              <button :aria-label="'取消排队 ' + item.content" @click="removeQueued(item.id)">×</button>
            </div>
          </div>
          <div v-if="busy" class="agent-followup-mode" role="group" aria-label="回复期间的新消息方式">
            <button :class="{ active: mode === 'queue' }" :aria-pressed="mode === 'queue'" @click="mode = 'queue'">排队</button>
            <button :class="{ active: mode === 'guide' }" :aria-pressed="mode === 'guide'" @click="mode = 'guide'">引导</button>
            <span>{{ mode === 'queue' ? '当前回复结束后发送' : '停止当前回复并立即处理' }}</span>
          </div>
          <form class="composer agent-composer" @submit.prevent="submit">
            <textarea v-model="input" aria-label="对话内容" placeholder="输入消息 · Enter 发送，Shift+Enter 换行" rows="3" maxlength="16000" @keydown="handleComposerKeydown"></textarea>
            <div class="section-heading agent-composer-footer">
              <span class="muted">{{ busy ? (mode === 'queue' ? '可继续输入并排队' : '将停止当前回复并处理新要求') : '当前回复会自动保存' }}</span>
              <div class="actions">
                <button v-if="busy" type="button" class="button subtle" @click="cancelCurrent()"><Square :size="14" /> 停止</button>
                <button type="submit" class="button primary icon-only" aria-label="发送" :disabled="!input.trim()">
                  <ArrowUp :size="20" />
                </button>
              </div>
            </div>
          </form>
        </div>
      </section>
    </div>
  </div>
</template>
