<script setup>
import { nextTick, ref } from 'vue'
import { ArrowUp, MessageCircle, Plus } from 'lucide-vue-next'
import { api } from '../api'
import { course, courseId } from '../session'

const messages = ref([])
const input = ref('')
const loading = ref(false)
const error = ref('')
const scrollTarget = ref(null)

async function send() {
  const value = input.value.trim()
  if (!value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const pending = [...messages.value, { role: 'user', content: value }]
    const response = await api('/agent/chat', {
      method: 'POST', body: {
        course_id: courseId.value,
        messages: pending.slice(-20).map(({ role, content }) => ({ role, content })),
      },
    })
    messages.value = [...pending, {
      role: 'assistant', content: response.text, maps: response.created_mind_maps, exams: response.created_exams,
    }]
    input.value = ''
    await nextTick()
    scrollTarget.value?.scrollIntoView({ block: 'nearest' })
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
}
</script>

<template>
  <div class="page agent-page">
    <header class="page-heading"><div><h1>教师 Agent</h1><p>{{ course.name }}</p></div><button class="button secondary" :disabled="loading || !messages.length" @click="messages = []; error = ''"><Plus :size="16" /> 新对话</button></header>
    <div class="agent-body">
      <div v-if="!messages.length" class="agent-empty"><span class="agent-icon"><MessageCircle :size="28" /></span><h2>教师 Agent</h2></div>
      <div v-else class="conversation" aria-live="polite">
        <div v-for="(message, index) in messages" :key="index" class="message" :class="message.role">
          {{ message.content }}
          <RouterLink v-for="map in message.maps" :key="map.id" class="text-link" :to="`/mind-maps/${map.id}`">打开导图「{{ map.title }}」</RouterLink>
          <RouterLink v-for="exam in message.exams" :key="exam.id" class="text-link" :to="`/exams/${exam.id}`">打开试卷「{{ exam.title }}」</RouterLink>
        </div>
        <span ref="scrollTarget"></span>
      </div>
      <form class="composer" @submit.prevent="send">
        <textarea v-model="input" aria-label="对话内容" placeholder="输入消息" rows="3" maxlength="5000" @keydown.ctrl.enter.prevent="send"></textarea>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="section-heading"><span class="muted">{{ loading ? '正在处理' : course.name }}</span><button type="submit" class="button primary icon-only" aria-label="发送" :disabled="loading || !input.trim()"><ArrowUp :size="20" /></button></div>
      </form>
    </div>
  </div>
</template>
