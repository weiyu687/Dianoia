<script setup>
import { onMounted, ref } from 'vue'
import { ArrowRight, ArrowUpRight, BookOpen, Files, MessagesSquare, Plus, Upload } from 'lucide-vue-next'
import { api, formatDate } from '../api'
import { course, courseId } from '../session'

const resources = ref([])
const lessons = ref([])
const error = ref('')
onMounted(async () => {
  try {
    const [resourceRows, lessonRows] = await Promise.all([
      api(`/resources?course_id=${courseId.value}`), api(`/lessons?course_id=${courseId.value}`),
    ])
    resources.value = resourceRows.slice(0, 3)
    lessons.value = lessonRows.filter((row) => row.status !== 'archived').slice(0, 3)
  } catch (failure) { error.value = failure.message }
})
</script>

<template>
  <div class="page home">
    <section class="hero">
      <div class="hero-art" aria-hidden="true"><div class="art-orbit orbit-a"></div><div class="art-orbit orbit-b"></div><div class="art-orbit orbit-c"></div><div class="hero-grid"></div></div>
      <div class="hero-copy">
        <span class="hero-course">{{ course.name }}</span>
        <h1>开始备课</h1>
        <div class="actions">
          <RouterLink class="button primary" to="/lessons?create=1"><Plus :size="18" /> 新建教案</RouterLink>
          <RouterLink class="button hero-button" to="/resources?upload=1"><Upload :size="17" /> 上传资料</RouterLink>
        </div>
      </div>
      <RouterLink class="hero-agent" to="/agent" aria-label="打开教师 Agent"><MessagesSquare :size="19" /><span>教师 Agent</span><ArrowUpRight :size="16" /></RouterLink>
    </section>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <section class="dashboard-grid">
      <div class="dashboard-section">
        <header class="section-heading"><h2><Files :size="20" /> 最近资料</h2><RouterLink to="/resources" class="text-link">管理资料 <ArrowRight :size="15" /></RouterLink></header>
        <div class="card-list">
          <RouterLink v-for="item in resources" :key="item.id" class="recent-row" :to="`/resources/${item.id}`">
            <span class="file-icon">{{ item.extension.toUpperCase() }}</span><div><strong>{{ item.title }}</strong><small>{{ formatDate(item.updated_at) }}</small></div><ArrowUpRight :size="15" />
          </RouterLink>
          <div v-if="!resources.length" class="recent-empty">当前课程暂无资料。<RouterLink to="/resources?upload=1">上传第一份资料</RouterLink></div>
        </div>
      </div>
      <div class="dashboard-section">
        <header class="section-heading"><h2><BookOpen :size="20" /> 最近教案</h2><RouterLink to="/lessons" class="text-link">管理教案 <ArrowRight :size="15" /></RouterLink></header>
        <div class="card-list">
          <RouterLink v-for="item in lessons" :key="item.id" class="recent-row" :to="`/lessons/${item.id}`">
            <span class="file-icon lesson-icon"><BookOpen :size="20" /></span><div><strong>{{ item.title }}</strong><small>{{ formatDate(item.updated_at) }}</small></div><ArrowUpRight :size="15" />
          </RouterLink>
          <div v-if="!lessons.length" class="recent-empty">当前课程暂无教案。<RouterLink to="/lessons?create=1">新建第一份教案</RouterLink></div>
        </div>
      </div>
    </section>
  </div>
</template>
